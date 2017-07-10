python train.py  \
--data-dir /home/zack/Data/LITS/ \
--data-list  /home/zack/Data/LITS/dataset/train.txt  \
--val-data-list /home/zack/Data/LITS/dataset/val.txt  \
--batch-size 4 \
--num-classes 3 \
--input-size '512,512'  \
--restore-from './snapshots/LITS4t2' \
--snapshot-dir './snapshots/LITS4t2_refine' \
--gpu-mask '1'  \
--num-steps 290045 \
