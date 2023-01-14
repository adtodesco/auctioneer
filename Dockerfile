FROM python:3.10-bullseye

WORKDIR /auctioneer

COPY auctioneer auctioneer
COPY requirements.txt .

RUN pip install -r requirements.txt
RUN python -m flask --app auctioneer init-db

CMD ["python", "-m", "gunicorn", "-b",  "0.0.0.0", "auctioneer:create_app()"]
