from nets import vgg16
import tensorflow as tf
import numpy as np
import utils

img = utils.load_image("./test_data/dog.jpg")

inputs = tf.placeholder(tf.float32, [None, None, 3])

resized_img = utils.resize_img(inputs, [224, 224])

prediction = vgg16.vgg_16(resized_img)

sess = tf.Session()
ckpt_filename = "./model/vgg_16.ckpt"
sess.run(tf.global_variables_initializer())
saver = tf.train.Saver()
saver.restore(sess, ckpt_filename)

pro = tf.nn.softmax(prediction)
pre = sess.run(pro, feed_dict={inputs: img})
print("results:")
utils.print_prob(pre[0], './synset.txt')
