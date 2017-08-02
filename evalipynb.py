import fnmatch
import itertools
import multiprocessing
import os

import nibabel as nb
import numpy as np
from medpy import metric

from surface import Surface


def get_scores(pred, label, vxlspacing):
    volscores = {}

    volscores['dice'] = metric.dc(pred, label)
    volscores['jaccard'] = metric.binary.jc(pred, label)
    volscores['voe'] = 1. - volscores['jaccard']
    volscores['rvd'] = metric.ravd(label, pred)

    if np.count_nonzero(pred) == 0 or np.count_nonzero(label) == 0:
        volscores['assd'] = 0
        volscores['msd'] = 0
    else:
        evalsurf = Surface(pred, label, physical_voxel_spacing=vxlspacing, mask_offset=[0., 0., 0.],
                           reference_offset=[0., 0., 0.])
        volscores['assd'] = evalsurf.get_average_symmetric_surface_distance()

        volscores['msd'] = metric.hd(label, pred, voxelspacing=vxlspacing)

    return volscores


def compute((label, prob)):
    loaded_label = nb.load(label)
    loaded_prob = nb.load(prob)

    liver_scores = get_scores(loaded_prob.get_data() >= 1, loaded_label.get_data() >= 1,
                              loaded_label.header.get_zooms()[:3])
    lesion_scores = get_scores(loaded_prob.get_data() == 2, loaded_label.get_data() == 2,
                               loaded_label.header.get_zooms()[:3])
    print prob, "Liver dice", liver_scores['dice'], "Lesion dice", lesion_scores['dice']

    # create line for csv file
    outstr = str(label) + ','
    for l in [liver_scores, lesion_scores]:
        for k, v in l.iteritems():
            outstr += str(v) + ','
        outstr += '\n'

    headerstr = 'Volume,'
    for k, v in liver_scores.iteritems():
        headerstr += 'Liver_' + k + ','
    for k, v in liver_scores.iteritems():
        headerstr += 'Lesion_' + k + ','
    headerstr += '\n'

    return outstr, headerstr


label_path = ''
prob_path = '/mnt/data/trainoutput/aug1'

# labels = sorted(glob.glob(label_path + 'label*.nii'))


probs = []
for root, dirnames, filenames in os.walk(prob_path):
    for filename in fnmatch.filter(filenames, '*.nii'):
        probs.append(os.path.join(root, filename))

print(probs)

labels = ['/mnt/data/LITS/Training Batch 2/segmentation-99.nii'] * len(probs)

outpath = './data/results.csv'
if not os.path.exists('./data/'):
    os.mkdir('./data/')

p = multiprocessing.Pool(4)
retval = p.map(compute, zip(labels, probs))
p.close()

list_results = list(itertools.chain.from_iterable([sublist[0] for sublist in retval]))
list_header = list(itertools.chain.from_iterable([sublist[1] for sublist in retval]))

# create header for csv file if necessary
if not os.path.isfile(outpath):
    with open(outpath, 'a+') as csvout:
        csvout.write(list_header[0])

with open(outpath, 'a+') as csvout:
    csvout.writelines(list_results)
