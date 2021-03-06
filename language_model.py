import tensorflow as tf
import numpy as np

from model_utils import sharded_variable, LSTMCell
from common import assign_to_gpu, average_grads, find_trainable_variables
from hparams import HParams


class LM(object):
    def __init__(self, hps, mode="train", ps_device="/gpu:0"):
        self.hps = hps
        self.global_step = tf.get_variable("global_step", [], tf.int32, initializer=tf.zeros_initializer,
                                           trainable=False)
        data_size = hps.batch_size * hps.num_gpus
        self.x = tf.placeholder(tf.int32, [data_size, hps.num_steps])
        if mode=="generate":
            xs = tf.split(0, hps.num_gpus, self.x)
            self.generated = []
            for i in range(hps.num_gpus):
                with tf.device(assign_to_gpu(i, ps_device)), tf.variable_scope(tf.get_variable_scope(),
                                                                           reuse=True if i > 0 else None):
                    self.generated.append(self.generate(i,xs[i],hps.num_g))
        else:
            self.y = tf.placeholder(tf.int32, [data_size, hps.num_steps])
            self.w = tf.placeholder(tf.int32, [data_size, hps.num_steps])

            losses = []
            tower_grads = []
            xs = tf.split(0, hps.num_gpus, self.x)
            ys = tf.split(0, hps.num_gpus, self.y)
            ws = tf.split(0, hps.num_gpus, self.w)
            for i in range(hps.num_gpus):
                with tf.device(assign_to_gpu(i, ps_device)), tf.variable_scope(tf.get_variable_scope(),
                                                                           reuse=True if i > 0 else None):
                    loss = self._forward(i, xs[i], ys[i], ws[i])
                    losses += [loss]
                    if mode == "train":
                        cur_grads = self._backward(loss, summaries=(i == hps.num_gpus - 1))
                        tower_grads += [cur_grads]


            if hps.eval_type == 'normal':
                self.loss = tf.add_n(losses) / len(losses)
                tf.scalar_summary("model/loss", self.loss)
            else:
                self.loss = losses


            if mode == "train":
                grads = average_grads(tower_grads)
                optimizer = tf.train.AdagradOptimizer(hps.learning_rate, initial_accumulator_value=1.0)
                self.train_op = optimizer.apply_gradients(grads, global_step=self.global_step)
                self.summary_op = tf.merge_all_summaries()
            else:
                self.train_op = tf.no_op()

            if mode in ["train", "eval"] and hps.average_params:
                with tf.name_scope(None):  # This is needed due to EMA implementation silliness.
                    # Keep track of moving average of LSTM variables.
                    ema = tf.train.ExponentialMovingAverage(decay=0.999)
                    variables_to_average = find_trainable_variables("LSTM")
                    self.train_op = tf.group(*[self.train_op, ema.apply(variables_to_average)])
                    self.avg_dict = ema.variables_to_restore(variables_to_average)

    # hps.eval_type: top_1, top_5, rank, normal, all
    # return batch_size*num_steps except when eval_type = 'normal'
    def _forward(self, gpu, x, y, w):
        hps = self.hps
        w = tf.to_float(w)
        self.initial_states = []
        for i in range(hps.num_layers):
            with tf.device("/gpu:%d" % gpu):
                v = tf.Variable(tf.zeros([hps.batch_size, hps.state_size + hps.projected_size]), trainable=False,
                                collections=[tf.GraphKeys.LOCAL_VARIABLES], name="state_%d_%d" % (gpu, i))
                self.initial_states += [v]

        emb_vars = sharded_variable("emb", [hps.vocab_size, hps.emb_size], hps.num_shards)

        x = tf.nn.embedding_lookup(emb_vars, x)  # [bs, steps, emb_size]
        if hps.keep_prob < 1.0:
            x = tf.nn.dropout(x, hps.keep_prob)

        inputs = [tf.squeeze(v, [1]) for v in tf.split(1, hps.num_steps, x)]

        for i in range(hps.num_layers):
            with tf.variable_scope("lstm_%d" % i):
                cell = LSTMCell(hps.state_size, hps.emb_size, num_proj=hps.projected_size) if i == 0 else LSTMCell(
                    hps.state_size, hps.projected_size, num_proj=hps.projected_size)

            state = self.initial_states[i]
            for t in range(hps.num_steps):
                inputs[t], state = cell(inputs[t], state)
                if hps.keep_prob < 1.0:
                    inputs[t] = tf.nn.dropout(inputs[t], hps.keep_prob)

            with tf.control_dependencies([self.initial_states[i].assign(state)]):
                inputs[t] = tf.identity(inputs[t])

        inputs = tf.reshape(tf.concat(1, inputs), [-1, hps.projected_size])

        # Initialization ignores the fact that softmax_w is transposed. That worked slightly better.
        softmax_w = sharded_variable("softmax_w", [hps.vocab_size, hps.projected_size], hps.num_shards)
        softmax_b = tf.get_variable("softmax_b", [hps.vocab_size])

        if hps.eval_type == 'top_1' or hps.eval_type == 'top_5' or hps.eval_type == 'rank':
            full_softmax_w = tf.reshape(tf.concat(1, softmax_w), [-1, hps.projected_size])
            full_softmax_w = full_softmax_w[:hps.vocab_size, :]

            logits = tf.matmul(inputs, full_softmax_w, transpose_b=True) + softmax_b  # (batch_size*step)*vocab
            targets = tf.reshape(y, [-1])
            if hps.eval_type == 'top_1':
                precision = tf.nn.in_top_k(logits, targets, 1)
                return tf.reshape(precision, tf.shape(y))
            elif hps.eval_type == 'top_5':
                precision = tf.nn.in_top_k(logits, targets, 5)
                return tf.reshape(precision, tf.shape(y))
            elif hps.eval_type == 'rank':
                values, indices = tf.nn.top_k(logits, hps.vocab_size)
                print('indices:',indices)
                targets =  tf.reshape(targets,(hps.batch_size*hps.num_steps,1))#+tf.zeros((hps.batch_size*hps.num_steps,hps.vocab_size),tf.int32)
                print('targets:',targets)
                print('indices==targets:',tf.equal(targets, indices))
                mat = tf.argmax(tf.cast(tf.equal(targets, indices),tf.int32), 1)
                return tf.reshape(mat, tf.shape(y))

        # compute cross entropy loss
        if hps.num_sampled == 0:
            full_softmax_w = tf.reshape(tf.concat(1, softmax_w), [-1, hps.projected_size])
            full_softmax_w = full_softmax_w[:hps.vocab_size, :]

            logits = tf.matmul(inputs, full_softmax_w, transpose_b=True) + softmax_b
            # targets = tf.reshape(tf.transpose(self.y), [-1])
            targets = tf.reshape(y, [-1])
            loss = tf.nn.sparse_softmax_cross_entropy_with_logits(logits, targets)
        else:
            targets = tf.reshape(y, [-1, 1])
            loss = tf.nn.sampled_softmax_loss(softmax_w, softmax_b, tf.to_float(inputs),
                                              targets, hps.num_sampled, hps.vocab_size)

        if hps.eval_type == 'all':  # return loss for every word
            return tf.reshape(loss, (hps.batch_size, hps.num_steps))
        # return average loss
        return tf.reduce_mean(loss * tf.reshape(w, [-1]))

    def generate(self,gpu,x,num_g):
        hps = self.hps
        self.initial_states = []
        for i in range(hps.num_layers):
            with tf.device("/gpu:%d" % gpu):
                v = tf.Variable(tf.zeros([hps.batch_size, hps.state_size + hps.projected_size]), trainable=False,
                                collections=[tf.GraphKeys.LOCAL_VARIABLES], name="state_%d_%d" % (gpu, i))
                self.initial_states += [v]

        emb_vars = sharded_variable("emb", [hps.vocab_size, hps.emb_size], hps.num_shards)

        x = tf.nn.embedding_lookup(emb_vars, x)  # [bs, steps, emb_size]

        inputs = [tf.squeeze(v, [1]) for v in tf.split(1, hps.num_steps, x)]

        for i in range(hps.num_layers):
            with tf.variable_scope("lstm_%d" % i):
                cell = LSTMCell(hps.state_size, hps.emb_size, num_proj=hps.projected_size) if i == 0 else LSTMCell(
                    hps.state_size, hps.projected_size, num_proj=hps.projected_size)

            state = self.initial_states[i]
            for t in range(hps.num_steps):
                inputs[t], state = cell(inputs[t], state)
            self.initial_states[i] = state
            #with tf.control_dependencies([self.initial_states[i].assign(state)]):
            #    inputs[t] = tf.identity(inputs[t])

        # Initialization ignores the fact that softmax_w is transposed. That worked slightly better.
        softmax_w = sharded_variable("softmax_w", [hps.vocab_size, hps.projected_size], hps.num_shards)
        softmax_b = tf.get_variable("softmax_b", [hps.vocab_size])
        full_softmax_w = tf.reshape(tf.concat(1, softmax_w), [-1, hps.projected_size])
        full_softmax_w = full_softmax_w[:hps.vocab_size, :]

        # start generating
        dist=inputs[-1] # batch_size*proj_size
        g_ws=[]
        for i in range(num_g):
            logits = tf.matmul(dist, full_softmax_w, transpose_b=True) + softmax_b  # batch_size*vocab
            # mask unk
            masked = [9]
            values = np.ones((hps.batch_size,hps.vocab_size))
            values[:,masked] = 0
            logits *= values
            g_ws.append(tf.argmax(logits,1)) # batch_size
            w_e = tf.nn.embedding_lookup(emb_vars, g_ws[-1])  # [bs, emb_size]
            dist = w_e
            # update state
            for i in range(hps.num_layers):
                with tf.variable_scope("lstm_%d" % i,reuse=True):
                    cell = LSTMCell(hps.state_size, hps.emb_size, num_proj=hps.projected_size) if i == 0 else LSTMCell(
                        hps.state_size, hps.projected_size, num_proj=hps.projected_size)
                state = self.initial_states[i]
                dist, state = cell(dist, state)
                self.initial_states[i] = state
                #with tf.control_dependencies([self.initial_states[i].assign(state)]):
                #    dist = tf.identity(dist)
        return g_ws

    def _backward(self, loss, summaries=False):
        hps = self.hps

        loss = loss * hps.num_steps

        emb_vars = find_trainable_variables("emb")
        lstm_vars = find_trainable_variables("LSTM")
        softmax_vars = find_trainable_variables("softmax")

        all_vars = emb_vars + lstm_vars + softmax_vars
        grads = tf.gradients(loss, all_vars)
        orig_grads = grads[:]
        emb_grads = grads[:len(emb_vars)]
        grads = grads[len(emb_vars):]
        for i in range(len(emb_grads)):
            assert isinstance(emb_grads[i], tf.IndexedSlices)
            emb_grads[i] = tf.IndexedSlices(emb_grads[i].values * hps.batch_size, emb_grads[i].indices,
                                            emb_grads[i].dense_shape)

        lstm_grads = grads[:len(lstm_vars)]
        softmax_grads = grads[len(lstm_vars):]

        lstm_grads, lstm_norm = tf.clip_by_global_norm(lstm_grads, hps.max_grad_norm)
        clipped_grads = emb_grads + lstm_grads + softmax_grads
        assert len(clipped_grads) == len(orig_grads)

        if summaries:
            tf.scalar_summary("model/lstm_grad_norm", lstm_norm)
            tf.scalar_summary("model/lstm_grad_scale", tf.minimum(hps.max_grad_norm / lstm_norm, 1.0))
            tf.scalar_summary("model/lstm_weight_norm", tf.global_norm(lstm_vars))
            # for v, g, cg in zip(all_vars, orig_grads, clipped_grads):
            #     name = v.name.lstrip("model/")
            #     tf.histogram_summary(name + "/var", v)
            #     tf.histogram_summary(name + "/grad", g)
            #     tf.histogram_summary(name + "/clipped_grad", cg)

        return list(zip(clipped_grads, all_vars))

    @staticmethod
    def get_default_hparams():
        return HParams(
            batch_size=128,
            num_steps=20,
            num_shards=8,
            num_layers=1,
            learning_rate=0.2,
            max_grad_norm=10.0,
            num_delayed_steps=150,
            keep_prob=0.9,

            vocab_size=158451,
            emb_size=512,
            state_size=2048,
            projected_size=512,
            num_sampled=8192,
            num_gpus=1,

            average_params=True,
            run_profiler=False,

            eval_type='normal',
            num_g=50
        )
