# iptables-management-telegram-bot

Telegram bot for managing access to a Minecraft port on a remote host via `iptables`.

The bot:

- accepts commands only from admins listed in `ADMINS_IDS`
- shows the button `Добавить IP адрес`
- validates entered IP address
- connects to a target server over SSH using a private key
- applies `iptables` rules to allow only the specified IP to connect to port `25565`

## Features

- Admin-only access control (multiple admin IDs supported)
- Telegram button-based workflow
- IPv4/IPv6 validation using Python standard library
- SSH execution via `paramiko`
- Container-ready (`Dockerfile`, `docker-compose.template.yaml`)
- CI/CD workflow for build and deployment via GitHub Actions

## How It Works

After pressing `Добавить IP адрес`, the bot asks for an IP and executes the following commands on the target server:

```bash
iptables -D DOCKER-USER -p tcp --dport 25565 -j DROP
iptables -A DOCKER-USER -p tcp --dport 25565 -s <INPUT_IP> -j ACCEPT
iptables -A DOCKER-USER -p tcp --dport 25565 -j DROP
```

This sequence removes a previous default DROP rule, adds allowlist access for the provided IP, then restores the default DROP.

## Project Structure

```text
.
├── bot.py
├── Dockerfile
├── requirements.txt
├── docker-compose.template.yaml
└── .github/workflows/ci-cd.yaml
```

## Requirements

- Python 3.11+
- Telegram bot token (from BotFather)
- SSH access (host, username, private key) to the target server where `iptables` should be changed
- `iptables` installed on the target server

## Environment Variables

### Runtime variables for bot container

| Variable | Required | Example | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | `123456:ABC...` | Telegram bot token |
| `ADMINS_IDS` | yes | `123456789,987654321` | Comma-separated Telegram user IDs allowed to use bot |
| `MINECRAFT_CHAT_ID` | no | `123456789` | Reserved for project-specific notifications |
| `BOT_TARGET_SSH_HOST` | yes | `10.0.0.5` | Host where bot executes `iptables` |
| `BOT_TARGET_SSH_PORT` | no | `22` | SSH port for target host (default `22`) |
| `BOT_TARGET_SSH_USERNAME` | yes | `ubuntu` | SSH username for target host |
| `BOT_TARGET_SSH_PRIVATE_KEY` | yes | `<paste_private_key_here>` | SSH private key for target host |

Note: `BOT_TARGET_SSH_PRIVATE_KEY` can be passed as multiline content or as a single line with `\n`.

## Local Run (Without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN="<token>"
export ADMINS_IDS="123456789,987654321"
export BOT_TARGET_SSH_HOST="10.0.0.5"
export BOT_TARGET_SSH_PORT="22"
export BOT_TARGET_SSH_USERNAME="ubuntu"
export BOT_TARGET_SSH_PRIVATE_KEY="<paste_private_key_here>"

python bot.py
```

## Run With Docker

```bash
docker build -t iptables-management-telegram-bot:local .

docker run --rm -it \
	-e TELEGRAM_BOT_TOKEN="<token>" \
	-e ADMINS_IDS="123456789,987654321" \
	-e BOT_TARGET_SSH_HOST="10.0.0.5" \
	-e BOT_TARGET_SSH_PORT="22" \
	-e BOT_TARGET_SSH_USERNAME="ubuntu" \
	-e BOT_TARGET_SSH_PRIVATE_KEY="<paste_private_key_here>" \
	iptables-management-telegram-bot:local
```

Never store real private keys in the repository, examples, or commit history.

## CI/CD Variables (GitHub Actions)

The workflow expects two independent SSH contexts:

1. Deploy host SSH (where bot container is deployed)
2. Bot target SSH (where `iptables` rules are modified)

### Repository Variables (`Settings -> Secrets and variables -> Actions -> Variables`)

- `DOCKER_REPO`
- `ADMINS_IDS`
- `MINECRAFT_CHAT_ID`
- `DEPLOY_SSH_HOST`
- `DEPLOY_SSH_PORT`
- `DEPLOY_SSH_USERNAME`
- `BOT_TARGET_SSH_HOST`
- `BOT_TARGET_SSH_PORT`
- `BOT_TARGET_SSH_USERNAME`

### Repository Secrets (`Settings -> Secrets and variables -> Actions -> Secrets`)

- `TELEGRAM_BOT_TOKEN`
- `DOCKER_USERNAME`
- `DOCKER_PASSWORD`
- `DEPLOY_SSH_PRIVATE_KEY`
- `BOT_TARGET_SSH_PRIVATE_KEY`

## Security Notes

- Keep all private keys in GitHub Secrets only.
- Restrict `ADMINS_IDS` to trusted Telegram users.
- Consider replacing `AutoAddPolicy` with known host key verification for production-hardening.
- On the target server, use least-privilege SSH access where possible.

## Troubleshooting

- `Доступ запрещен.`
	- Ensure your Telegram user ID is present in `ADMINS_IDS`.
- `Некорректный ADMINS_IDS...`
	- Verify `ADMINS_IDS` is comma-separated integers only.
- SSH connection errors
	- Check host, port, username, and private key format.
- `iptables` command failed
	- Ensure the SSH user has enough privileges (`sudo` or root context may be required).

## License

See `LICENSE`.
