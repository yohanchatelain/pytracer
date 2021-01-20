FROM yohanchatelain/fuzzy:python-numpy-scipy-sklearn-v0.4.1

COPY . /opt/build/pytracer

RUN cd /opt/build/pytracer && pip install .

ENTRYPOINT [ "/bin/bash" ]