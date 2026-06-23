FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# git/ssh 가 uid 1000 의 사용자 정보를 찾을 수 있도록 계정 생성
RUN groupadd -g 1000 app && useradd -m -u 1000 -g 1000 -s /bin/bash app
WORKDIR /app
COPY writer.py /app/writer.py
ENV PORT=8080
USER app
EXPOSE 8080
CMD ["python", "/app/writer.py"]
