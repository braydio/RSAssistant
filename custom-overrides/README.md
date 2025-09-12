Copy custom-overrides/entrypoint.sh up one directory

`cp Override-RSA/custom-overrides/entrypoint.sh Override-RSA/entrypoint.sh`

Rebuild the bot

`docker-compose up --build`

Watch main auto-rsa repo for updates and changes, this override modifies:

- autoRSA.py
- entrypoint.sh
- docker-compose.yml

