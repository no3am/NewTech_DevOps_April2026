FROM alpine:3.22.2

# Update
RUN apk add --update python3

# Bundle app source
COPY client.py /src/client.py


ENTRYPOINT ["python3", "/src/client.py"]
