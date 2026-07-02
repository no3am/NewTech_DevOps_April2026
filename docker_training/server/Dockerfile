FROM alpine:3.22.2

# Update
RUN apk add --update python3 py3-pip

# Install app dependencies
RUN pip3 install --break-system-packages -U web.py

# Bundle app source
COPY server.py /src/server.py
COPY user_data.xml /src/user_data.xml

WORKDIR /src

EXPOSE  8080
CMD ["python3", "/src/server.py"]
