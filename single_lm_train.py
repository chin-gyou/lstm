import tensorflow as tf

from data_utils import Vocabulary, Dataset
from language_model import LM
from run_utils import run_train, run_eval, run_test

flags = tf.flags
flags.DEFINE_string("logdir", "../log", "Logging directory.")
flags.DEFINE_string("datadir", "../data", "Data directory.")
flags.DEFINE_string("mode", "train", "Whether to run 'train' or 'eval' model.")
flags.DEFINE_string("hpconfig", "", "Overrides default hyper-parameters.")
flags.DEFINE_integer("num_gpus", 1, "Number of GPUs used.")
flags.DEFINE_integer("eval_steps", 70, "Number of eval steps.")

FLAGS = flags.FLAGS


def main(_):
    hps = LM.get_default_hparams().parse(FLAGS.hpconfig)
    hps.num_gpus = FLAGS.num_gpus
    
    vocab = Vocabulary.from_file("pruned_vocab.txt")

    if FLAGS.mode == "train":
        dataset = Dataset(vocab, FLAGS.datadir + "/pruned/training/*")
        run_train(dataset, hps, FLAGS.logdir + "/train", ps_device="/gpu:0")
    elif FLAGS.mode == "test" or FLAGS.mode == "generate":
        data_dir = FLAGS.datadir + "/"+FLAGS.mode+".txt"
        dataset = Dataset(vocab, data_dir, deterministic=True)
        run_test(dataset,hps,FLAGS.logdir,FLAGS.mode)
    elif FLAGS.mode.startswith("eval_"):
        if FLAGS.mode.startswith("eval_train"):
            data_dir = FLAGS.datadir + "/pruned/training/*"
        else:
            data_dir = FLAGS.datadir + "/pruned/heldout/news.en.heldout-00000-of-00050.pruned"
        dataset = Dataset(vocab, data_dir, deterministic=True)
        run_eval(dataset, hps, FLAGS.logdir, FLAGS.mode, FLAGS.eval_steps)


if __name__ == "__main__":
    tf.app.run()
