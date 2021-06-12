FROM selenium/standalone-chrome

USER root
EXPOSE 8080

WORKDIR /app

RUN apt-get update && apt-get install -y python3-pip && apt-get clean && rm -rf /var/lib/apt/lists/*

ADD requirements.txt ./
RUN pip3 install --no-cache-dir --no-warn-script-location -r requirements.txt
ADD docker/.streamlit /home/seluser/.streamlit

ADD src src
CMD python3 -m streamlit run --server.fileWatcherType=none src/main.py