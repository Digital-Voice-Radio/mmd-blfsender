#!/bin/bash
#
apt update 
apt install -y python3 python3-virtualenv

virtualenv /opt/mmblfsender

/opt/mmblfsender/bin/pip install -r requirements.txt

cp *.py /opt/mmblfsender
if [ ! -f /opt/mmblfsender/config.py ]
then
	mv /opt/mmblfsender/config_SAMPLE.py /opt/mmblfsender/config.py
fi

cp system/mmblfsender.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mmblfsender
#systemctl start mmblfsender



