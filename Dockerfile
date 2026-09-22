FROM python:3.13-alpine

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

RUN apk add --no-cache su-exec tzdata
RUN adduser -D user

WORKDIR /opt/rdgen

COPY . .
RUN pip install --no-cache-dir -r requirements.txt \
 && chmod +x /opt/rdgen/entrypoint.sh

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget --spider 127.0.0.1:8000/healthz

ENTRYPOINT ["/opt/rdgen/entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "rdgen.wsgi:application"]
