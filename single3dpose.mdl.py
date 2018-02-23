# -*- coding: utf-8 -*-
import os
import random
import scipy.io as sio
import tensorflow as tf
import tensorflow.contrib.layers as layers
import numpy as np
import cv2
import myNet
import myNet_one_stage
import ParseTool
import datagen
from multiprocessing import Process
from Global import *


def cpm_model_train(base_lr, epochs, batch_size, hparam):
    #   list of summary
        tf.reset_default_graph()
        sess = tf.Session()
        summ_image = []
        summ_scalar = []
        #   Load train list from train_list.txt
        train_list = ParseTool.load_list(MPII_ROOT + "train_list.txt")

        global_step = tf.Variable(0, trainable=False)
        x = tf.placeholder(tf.float32, shape=[None, INPUT_SIZE, INPUT_SIZE, 3], name="x")
        x_image = tf.reshape(x, [-1, INPUT_SIZE, INPUT_SIZE, 3])
        y = tf.placeholder(tf.float32, shape=[None, INPUT_SIZE/8, INPUT_SIZE/8, 16])
        gtmap = tf.reshape(y, [-1, INPUT_SIZE/8, INPUT_SIZE/8, 16])

        #   Net structure
        #stagehmap = myNet.inference_pose(x_image)
        stagehmap = myNet_one_stage.inference_pose(x_image)

        #   calculate the return full map
        __all_gt = tf.expand_dims(tf.expand_dims(tf.reduce_sum(tf.transpose(gtmap, perm=[0,3,1,2])[0], axis=[0]), 0), 3)
        __image = tf.expand_dims(tf.transpose(x_image, perm=[0,3,1,2])[0], 3)
        summ_image.append(tf.summary.image("gtmap", __all_gt, max_outputs=1))
        summ_image.append(tf.summary.image("image", __image))

        for m in range(len(stagehmap)):
            #   __sample_pred have the shape of
            #   16 * INPUT+_SIZE/8 * INPUT_SIZE/8
            __sample_pred = tf.transpose(stagehmap[m], perm=[0,3,1,2])[0]
            print __sample_pred.shape
            #   __all_pred have shape of 
            #   INPUT_SIZE/8 * INPUT_SIZE/8
            __all_pred = tf.expand_dims(tf.expand_dims(tf.reduce_sum(tf.transpose(stagehmap[m], perm=[0,3,1,2])[0], axis=[0]), 0), 3)
            print __all_pred.shape
            summ_image.append(tf.summary.image("stage"+str(m)+" map", __all_pred, max_outputs=1))

        #   Optimizer
        with tf.name_scope('train'):
            losses = []
            #   step learning rate policy
            learning_rate = tf.train.exponential_decay(base_lr, global_step,1000, 0.333, staircase=True)
            train_step = []
            pFeature = tf.trainable_variables(scope='.*FeatureExtractor')
            assert pFeature != []
            for idx in range(len(stagehmap)):
                __para = []
                loss = tf.reduce_sum(tf.nn.l2_loss(
                    stagehmap[idx] - gtmap, name='loss_stage_%d' % idx))
                losses.append(loss)
                summ_scalar.append(tf.summary.scalar("loss in stage"+str(idx+1), loss))
                if idx == 0:
                    #   stage
                    __para = tf.trainable_variables(scope='.*CPM_stage'+str(idx+1)) + pFeature
                    assert __para != []
                    optimizer = tf.train.GradientDescentOptimizer(learning_rate)
                    grads_vars = optimizer.compute_gradients(loss, 
                                        var_list=__para)
                    train_step.append(optimizer.apply_gradients(grads_vars, 
                                        global_step=global_step))
                else:
                    __para += tf.trainable_variables(scope='.*CPM_stage'+str(idx+1))
                    assert __para != []
                    # Passing global_step to minimize() will increment it at each step
                    optimizer = tf.train.GradientDescentOptimizer(learning_rate)
                    grads_vars = optimizer.compute_gradients(loss, 
                                                var_list=__para)
                    #   lr_mult = 4
                    #grads_vars[0] = 4 * grads_vars[0]
                    train_step.append(optimizer.apply_gradients(grads_vars, 
                        global_step=global_step))

        #   merge all summary
        summ_image = tf.summary.merge(summ_image)
        summ_scalar = tf.summary.merge(summ_scalar)

        #   save the model every 500 iters
        saver = tf.train.Saver()

        sess.run(tf.global_variables_initializer())
        writer = tf.summary.FileWriter(LOGDIR + hparam)
        writer.add_graph(sess.graph)

        _epoch_count = 0
        _iter_count = 0
        for n in range(epochs):
            #   do an index shuffle
            #   every iter train 6 stage seprately
            #   for every index batches
            for step in train_step:
                idx_batches = ParseTool.shuffle(train_list[:], batch_size)
                for m in idx_batches:
                    _train_batch = ParseTool.__struct_mini_batch(m)
                    print "batch generated!"
                    sess.run(step, feed_dict={x: _train_batch[0],
                        y:_train_batch[1]})
                    _iter_count += 1
                    print "iter:", _iter_count
                    #   make image 1000 iter
                    if _iter_count % 1000 == 0:
                        writer.add_summary(
                            sess.run(summ_image,feed_dict={x: _train_batch[0], y:_train_batch[1]}))
                    if _iter_count % 50 == 0:
                        print "epoch ", _epoch_count, " iter ", _iter_count, sess.run(losses, feed_dict={x: _train_batch[0], y:_train_batch[1]})
                        #   write summary for every batch
                        writer.add_summary(
                            sess.run(summ_scalar,feed_dict={x: _train_batch[0], y:_train_batch[1]}),
                            _iter_count)
                    writer.flush()
            #   save model every epoch
            saver.save(sess, os.path.join(LOGDIR, "model.ckpt"), n)

def make_hparam_string(learning_rate, epoch):
    return "lr_%.0E, epoch: %d" % (learning_rate, epoch)


def main():
    hparam = make_hparam_string(
        base_lr, epoch)
    print('Starting run for %s' % hparam)

    # Actually run with the new settings
    cpm_model_train(base_lr, epoch, batch_size, hparam)


if __name__ == '__main__':
    main()