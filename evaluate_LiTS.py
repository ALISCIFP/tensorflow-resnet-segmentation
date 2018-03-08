import argparse
import glob
import os
import re
from multiprocessing import Process, Queue, Event

import cv2
import nibabel as nib
import numpy as np
import scipy.ndimage
import tensorflow as tf

from deeplab_resnet import ThreeDNetwork, ImageReader

IMG_MEAN = np.array((33.43633936, 33.38798846, 33.43324414), dtype=np.float32)  # LITS resmaple 0.6mm

DATA_DIRECTORY = None
DATA_LIST_PATH = None
IGNORE_LABEL = 255
NUM_CLASSES = 3
BATCH_SIZE = 1
RESTORE_FROM = None


def get_arguments():
    """Parse all the arguments provided from the CLI.

    Returns:
      A list of parsed arguments.
    """
    parser = argparse.ArgumentParser(description="DeepLabLFOV Network")
    parser.add_argument("--data-dir", type=str, default=DATA_DIRECTORY,
                        help="Path to the directory containing the PASCAL VOC dataset.")
    parser.add_argument("--threed-data-dir", type=str, default=DATA_DIRECTORY,
                        help="Path to the directory containing the PASCAL VOC dataset.")
    parser.add_argument("--data-list", type=str, default=DATA_LIST_PATH,
                        help="Path to the file listing the images in the dataset.")
    parser.add_argument("--ignore-label", type=int, default=IGNORE_LABEL,
                        help="The index of the label to ignore during the training.")
    parser.add_argument("--num-classes", type=int, default=NUM_CLASSES,
                        help="Number of classes to predict (including background).")
    parser.add_argument("--restore-from", type=str, default=RESTORE_FROM,
                        help="Where restore model parameters from.")
    parser.add_argument("--post-processing", action="store_true",
                        help="Post processing enable or disable")
    parser.add_argument("--batch_size", type=int, default=BATCH_SIZE,
                        help="Number of classes to predict (including background).")
    return parser.parse_args()


def load(saver, sess, ckpt_path):
    '''Load trained weights.

    Args:
      saver: TensorFlow saver object.
      sess: TensorFlow session.
      ckpt_path: path to checkpoint file with parameters.
    '''
    if '.ckpt' in ckpt_path:
        saver.restore(sess, ckpt_path)
    else:
        saver.restore(sess, tf.train.latest_checkpoint(ckpt_path))
    print("Restored model parameters from {}".format(ckpt_path))


def saving_process(queue, event, threed_data_dir, post_processing, restore_from):
    dict_of_curr_processing = {}
    dict_of_curr_processing_len = {}

    while not (event.is_set() and queue.empty()):
        key, idx, preds, num_slices = queue.get()
        if key not in dict_of_curr_processing:
            dict_of_curr_processing[key] = np.zeros((num_slices, preds.shape[0], preds.shape[1]), dtype=np.uint8)
            dict_of_curr_processing_len[key] = 1  # this is correct!

        dict_of_curr_processing[key][idx] = preds
        dict_of_curr_processing_len[key] += 1

        if dict_of_curr_processing_len[key] == num_slices:
            if post_processing:
                preds_liver = np.copy(dict_of_curr_processing[key])
                preds_liver[preds_liver == 2] = 1
                preds_liver = scipy.ndimage.morphology.binary_erosion(preds_liver.astype(np.uint8),
                                                                      np.ones((3, 3, 3), np.uint8), iterations=5)

                preds_lesion = np.copy(dict_of_curr_processing[key])
                preds_lesion[preds_lesion == 1] = 0
                preds_lesion[preds_lesion == 2] = 1
                preds_lesion = scipy.ndimage.morphology.binary_dilation(preds_lesion.astype(np.uint8),
                                                                        np.ones((3, 3, 3), np.uint8), iterations=5)
                dict_of_curr_processing[key] = preds_lesion.astype(np.uint8) + preds_liver.astype(np.uint8)

            fname_out = os.path.join(restore_from, 'eval/niiout/' + key.replace('volume', 'segmentation') + '.nii')
            print("Writing: " + fname_out)
            path_to_img = glob.glob(threed_data_dir + '/*/' + key + '.nii')
            print(path_to_img)
            assert len(path_to_img) == 1

            img = nib.load(path_to_img[0])
            nii_out = nib.Nifti1Image(dict_of_curr_processing[key], img.affine, header=img.header)
            nii_out.set_data_dtype(np.uint8)
            nib.save(nii_out, fname_out)
            del dict_of_curr_processing[key]
            dict_of_curr_processing_len[key] += 1


def main():
    """Create the model and start the evaluation process."""

    args = get_arguments()
    print(args)

    if not os.path.exists(os.path.join(args.restore_from, 'eval/niiout')):
        os.makedirs(os.path.join(args.restore_from, 'eval/niiout'))
    if not os.path.exists(os.path.join(args.restore_from, 'eval/pngout')):
        os.makedirs(os.path.join(args.restore_from, 'eval/pngout'))

    event_end = Event()
    queue_proc = Queue()
    with open(args.data_list, 'r') as f:
        list_of_all_lines = f.readlines()
        f.seek(0)

        dict = {}
        for line in f:
            if re.match(".*\\/(.*)\\.nii.*", line).group(1) not in dict:
                dict[re.match(".*\\/(.*)\\.nii.*", line).group(1)] = []

            dict[re.match(".*\\/(.*)\\.nii.*", line).group(1)].append(line.rsplit()[0])

        with tf.Graph().as_default():
            # Create queue coordinator.
            coord = tf.train.Coordinator()

            # Load reader.
            with tf.name_scope("create_inputs"):
                reader = ImageReader(
                    args.data_dir,
                    args.data_list,
                    None,  # No defined input size.
                    False,  # No random scale.
                    False,  # No random mirror.
                    args.ignore_label,
                    IMG_MEAN,
                    coord,
                    shuffle=False)
                image = tf.cast(reader.image, tf.float32)

            image_batch = tf.concat(tf.split(tf.expand_dims(image, axis=0), 12, axis=-1), axis=0)
            image_batch = tf.image.resize_bilinear(image_batch, [224, 224])  # Add one batch dimension.

            # Create network.
            net = ThreeDNetwork({'data': image_batch}, is_training=False, num_classes=args.num_classes)

            # Which variables to load.
            restore_var = tf.global_variables()

            # Predictions.
            raw_output = tf.squeeze(net.layers['3d_conv2'], axis=0)
            raw_output = tf.image.resize_bilinear(raw_output, [512, 512])
            raw_output = tf.argmax(raw_output, axis=3)

            sess = tf.Session()
            sess.run(tf.group(tf.global_variables_initializer(), tf.local_variables_initializer()))

            # Load weights.
            loader = tf.train.Saver(var_list=restore_var)
            load(loader, sess, args.restore_from)

            # Start queue threads.
            proc = Process(target=saving_process, args=(queue_proc, event_end,
                                                        args.threed_data_dir, args.post_processing, args.restore_from))
            proc.start()
            threads = tf.train.start_queue_runners(coord=coord, sess=sess)

            for sublist in [list_of_all_lines[i:i + args.batch_size] for i in
                            xrange(0, len(list_of_all_lines), args.batch_size)]:
                preds = sess.run([raw_output])[0][5:6]
                for i, thing in enumerate(sublist):
                    regex_match = re.match(".*\\/(.*)\\.nii_([0-9]+).*", thing)
                    # print(regex_match.group(1) + ' ' + str(regex_match.group(2)))
                    cv2.imwrite(os.path.join(args.restore_from, 'eval/pngout', regex_match.group(1).replace('volume',
                                                                                                            'segmentation') + ".nii_" + regex_match.group(
                        2) + ".png"), preds[i])
                    queue_proc.put(
                        (regex_match.group(1), int(regex_match.group(2)), preds[i], len(dict[regex_match.group(1)])))

            coord.request_stop()
            coord.join(threads)
            event_end.set()
            proc.join()


if __name__ == '__main__':
    main()
