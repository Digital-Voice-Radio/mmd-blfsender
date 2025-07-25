#!/bin/bash
#
#
LOG=/tmp/mmblfsender-install.log
echo ┏┳┓┏┳┓╺┳┓┏━┓┏━╸┏┓╻╺┳┓┏━╸┏━┓   ┏┓ ╻  ┏━╸
echo ┃┃┃┃┃┃ ┃┃┗━┓┣╸ ┃┗┫ ┃┃┣╸ ┣┳┛╺━╸┣┻┓┃  ┣╸ 
echo ╹ ╹╹ ╹╺┻┛┗━┛┗━╸╹ ╹╺┻┛┗━╸╹┗╸   ┗━┛┗━╸╹ 
echo
echo Verbose Output logged to $LOG
echo Install Started > ${LOG}

if [ ! -d /opt/mmblfsender ]
then
	echo ------------------------
	echo Initial Install
	echo ------------------------
	echo Running apt-update...
	apt update >> ${LOG}
	echo Installing python3 python3-virtualenv...
	apt install -y python3 python3-virtualenv >> ${LOG}

	echo Creating virtualenv...
	virtualenv /opt/mmblfsender >> ${LOG}
	echo Setting up systemd...

	cp system/mmblfsender.service /etc/systemd/system/
	systemctl daemon-reload
else
	echo Running an update only as /opt/mmblfsender exists
	echo -------------------------------------------------
fi

echo Updating virtualenv dependencies
/opt/mmblfsender/bin/pip install -r requirements.txt >> $LOG

echo Updating Application
cp *.py /opt/mmblfsender

if [ ! -f /opt/mmblfsender/config.py ]
then
	echo Copying Sample configuration.  Please modify /opt/mmblfsender/config.py
	mv /opt/mmblfsender/config_SAMPLE.py /opt/mmblfsender/config.py
fi

echo Enabling systemd service

systemctl enable mmblfsender



