server = None
channel = not message.channel.id in bot.off_channels -- create or get

# New TRY: info: parse secondary Feed message format with ticker url
if message.channel.id == DISCORD_SECOND_CHANNEL:
    if message.content:
        content = message.content
        res = alert_channel_message(content)
        if res and res.get("reverse-split-confirm"):
            alert_ticker = res.get("ticker")
            alert_url = res.get("url")
            main_channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
            if main_channel:
                await main_channel.send(
                    f"Reverse Split Alert for {alert_ticker} - {alert_url}"
                )
                logging.info("Alert Message Sent to Primary Channel"))
            else:
                logging.warning(
                    "No match found in content for alert message. Content may not follow the expected pattern."
                )
