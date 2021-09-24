FROM ubuntu:20.04

RUN apt-get -y update && apt-get -y --no-install-recommends install tzdata
RUN apt-get -y install --no-install-recommends gcc python3.8 python3.8-dev python3-pip && \
    rm -rf /var/lib/apt/lists/*

COPY . /opt/build/pytracer

RUN cd /opt/build/pytracer && \
    python3 -m pip install . -r requirements.txt

ENTRYPOINT [ "/bin/bash" ]