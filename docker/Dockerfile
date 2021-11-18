FROM ubuntu:20.04

RUN apt-get -y update && apt-get -y --no-install-recommends install tzdata
RUN apt-get -y install --no-install-recommends git gcc python3.8 python3.8-dev python3-pip && \
    rm -rf /var/lib/apt/lists/*

COPY . /opt/build/pytracer

RUN git clone https://github.com/verificarlo/significantdigits.git /opt/build/significantdigits && \
    cd /opt/build/significantdigits && \
    python3 -m pip install . -r requirements.txt

RUN cd /opt/build/pytracer && \
    python3 -m pip install . -r requirements.txt && \
    python3 -m pip freeze

ENTRYPOINT [ "/bin/bash" ]