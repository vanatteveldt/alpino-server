# This is a comment
FROM rugcompling/alpino:latest
MAINTAINER Wouter van Atteveldt (wouter@vanatteveldt.com)
EXPOSE 5002

RUN apt-get -qq update && apt-get install -y python3-flask
COPY alpinoserver.py .

CMD python3 alpinoserver.py --host 0.0.0.0 --port 5002 --debug
