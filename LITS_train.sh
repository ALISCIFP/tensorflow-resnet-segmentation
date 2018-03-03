python train.py  \
--data-dir /home/zack/Data/paperLITS \
--data-list /home/zack/Data/paperLITS/dataset/train.txt \
--val-data-list /home/zack/Data/paperLITS/dataset/val.txt \
--snapshot-dir './snapshots/HanResNet5Slices_320' \
--gpu-mask '0,1' \
--batch-size 5 \
--learning-rate 2.5e-4 \
--input-size '320,320' \
--random-scale \
--random-mirror \
--num-steps 118955 \