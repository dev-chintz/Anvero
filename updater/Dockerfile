# The updater (server.py): the Docker command line with its compose plugin,
# and Python to run the small server that calls it.
FROM docker:cli

RUN apk add --no-cache python3

WORKDIR /app
COPY server.py .

EXPOSE 8080

CMD ["python3", "server.py"]
