FROM python:3.10-bullseye

RUN apt-get update && apt-get -y install cron

WORKDIR /auctioneer

COPY auctioneer auctioneer
COPY requirements.txt .

RUN pip install -r requirements.txt
RUN python -m flask --app auctioneer init-db

COPY auctioneer-cron /etc/cron.d/auctioneer-cron
RUN chmod 0644 /etc/cron.d/auctioneer-cron
RUN crontab /etc/cron.d/auctioneer-cron
RUN touch /var/log/cron.log

CMD env >> /etc/environment && cron && python -m gunicorn -b 0.0.0.0 auctioneer:create_app\(\)
