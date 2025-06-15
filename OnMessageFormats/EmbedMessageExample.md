# Channel Messages

---

RS Assistant
APP
— 9:01 AM
Clearing the current holdings for refresh.
Holdings at: "/home/braydenchaffee/Projects/RSA-Production/volumes/logs/holdings_log.csv" has been cleared. Run !rsa holdings to repopulate.
Watchlist - Upcoming Split Dates:
Repeat this message with '..reminder'
!rsa holdings all
Money Printer 5000
APP
— 9:02 AM
BBAE Holdings
BBAE 1 (xxxx4365)
K016130: 1.0 @ $0.00 = $0.00
NCNCF: 1.0 @ $0.00 = $0.00
PTPI: 1.0 @ $0.03 = $0.03
Total: $107.74
BBAE 2 (xxxx4837)
K016130: 1.0 @ $0.00 = $0.00
NCNCF: 1.0 @ $0.00 = $0.00
PTPI: 1.0 @ $0.03 = $0.03
Total: $53.35
BBAE 3 (xxxx5363)
PTPI: 1.0 @ $0.03 = $0.03
Total: $28.17
DSPAC Holdings
DSPAC 1 (xxxx9768)
PTPI: 1.0 @ $0.03 = $0.03
Total: $55.63
DSPAC 3 (xxxx0150)
PTPI: 1.0 @ $0.03 = $0.03
Total: $55.20

# Logs

---

2025-06-15 09:02:00,113 - INFO - Parsing regular order message.
2025-06-15 09:02:00,113 - ERROR - No match found for message: Holdings at: "/home/braydenchaffee/Projects/RSA-Production/volumes/logs/holdings_log.csv" has been cleared. Run `!rsa holdings` to repopulate.
2025-06-15 09:02:00,221 - INFO - Sending reminder message at 2025-06-15 09:02:00.221591
2025-06-15 09:02:00,221 - INFO - Updating historical holdings based on live data.
2025-06-15 09:02:00,225 - INFO - Historical holdings updated successfully.
2025-06-15 09:02:00,225 - INFO - Reminder message called for 2025-06-15 09:02:00.225381
2025-06-15 09:02:00,225 - INFO - Updating historical holdings based on live data.
2025-06-15 09:02:00,228 - INFO - Historical holdings updated successfully.
2025-06-15 09:02:00,369 - INFO - Received message: <Message id=1383793668875485295 channel=<TextChannel id=1275345611813814334 name='auto-rsa' position=3 nsfw=False news=False category_id=1275343878744047637> type=<MessageType.default: 0> author=<Member id=1275369263477166080 name='Order Flowbot' global_name=None bot=True nick='RS Assistant' guild=<Guild id=1275343878744047636 name='Stocks and Stuff' shard_id=0 chunked=True member_count=12>> flags=<MessageFlags value=0>>
2025-06-15 09:02:00,370 - INFO - Embed message detected.
2025-06-15 09:02:00,370 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:00,370 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:00,370 - ERROR - Failed to parse embedded holdings
2025-06-15 09:02:00,724 - INFO - Received message: <Message id=1383793670364332104 channel=<TextChannel id=1275345611813814334 name='auto-rsa' position=3 nsfw=False news=False category_id=1275343878744047637> type=<MessageType.default: 0> author=<Member id=1275369263477166080 name='Order Flowbot' global_name=None bot=True nick='RS Assistant' guild=<Guild id=1275343878744047636 name='Stocks and Stuff' shard_id=0 chunked=True member_count=12>> flags=<MessageFlags value=0>>
2025-06-15 09:02:00,725 - INFO - Parsing regular order message.
2025-06-15 09:02:00,725 - ERROR - No match found for message: !rsa holdings all
2025-06-15 09:02:30,773 - INFO - Received message: <Message id=1383793796369879142 channel=<TextChannel id=1275345611813814334 name='auto-rsa' position=3 nsfw=False news=False category_id=1275343878744047637> type=<MessageType.default: 0> author=<Member id=1275344080993386599 name='Money Printer 5000' global_name=None bot=True nick=None guild=<Guild id=1275343878744047636 name='Stocks and Stuff' shard_id=0 chunked=True member_count=12>> flags=<MessageFlags value=0>>
2025-06-15 09:02:30,773 - INFO - Embed message detected.
2025-06-15 09:02:30,773 - INFO - [{'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'K016130', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '107.74'}, {'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'NCNCF', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '107.74'}, {'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '107.74'}]
2025-06-15 09:02:30,773 - INFO - [{'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'K016130', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '107.74'}, {'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'NCNCF', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '107.74'}, {'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '107.74'}, {'account_name': 'BBAE (Lem) Cash Account 1', 'broker': 'BBAE', 'group': '2', 'account': '4837', 'ticker': 'K016130', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '53.35'}, {'account_name': 'BBAE (Lem) Cash Account 1', 'broker': 'BBAE', 'group': '2', 'account': '4837', 'ticker': 'NCNCF', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '53.35'}, {'account_name': 'BBAE (Lem) Cash Account 1', 'broker': 'BBAE', 'group': '2', 'account': '4837', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '53.35'}]
2025-06-15 09:02:30,774 - INFO - [{'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'K016130', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '107.74'}, {'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'NCNCF', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '107.74'}, {'account_name': 'BBAE (Chaf) Cash Account 1', 'broker': 'BBAE', 'group': '1', 'account': '4365', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '107.74'}, {'account_name': 'BBAE (Lem) Cash Account 1', 'broker': 'BBAE', 'group': '2', 'account': '4837', 'ticker': 'K016130', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '53.35'}, {'account_name': 'BBAE (Lem) Cash Account 1', 'broker': 'BBAE', 'group': '2', 'account': '4837', 'ticker': 'NCNCF', 'quantity': '1.0', 'price': '0.00', 'value': '0.00', 'account_total': '53.35'}, {'account_name': 'BBAE (Lem) Cash Account 1', 'broker': 'BBAE', 'group': '2', 'account': '4837', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '53.35'}, {'account_name': 'BBAE (Dre) Cash Account 1', 'broker': 'BBAE', 'group': '3', 'account': '5363', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '28.17'}]
2025-06-15 09:02:30,774 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:30,774 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:30,774 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:30,774 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:30,774 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:30,774 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:30,774 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:30,774 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:30,774 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:30,774 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:30,774 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:30,774 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:30,774 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:30,774 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:33,158 - INFO - Received message: <Message id=1383793806515900518 channel=<TextChannel id=1275345611813814334 name='auto-rsa' position=3 nsfw=False news=False category_id=1275343878744047637> type=<MessageType.default: 0> author=<Member id=1275344080993386599 name='Money Printer 5000' global_name=None bot=True nick=None guild=<Guild id=1275343878744047636 name='Stocks and Stuff' shard_id=0 chunked=True member_count=12>> flags=<MessageFlags value=0>>
2025-06-15 09:02:33,158 - INFO - Embed message detected.
2025-06-15 09:02:33,158 - INFO - [{'account_name': 'DSPAC (Chaf) Cash Account 1', 'broker': 'DSPAC', 'group': '1', 'account': '9768', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '55.63'}]
2025-06-15 09:02:33,158 - INFO - [{'account_name': 'DSPAC (Chaf) Cash Account 1', 'broker': 'DSPAC', 'group': '1', 'account': '9768', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '55.63'}, {'account_name': 'DSPAC DSPAC 3 0150', 'broker': 'DSPAC', 'group': '3', 'account': '0150', 'ticker': 'PTPI', 'quantity': '1.0', 'price': '0.03', 'value': '0.03', 'account_total': '55.20'}]
2025-06-15 09:02:33,158 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:33,158 - ERROR - No holdings were parsed from the embed message.
2025-06-15 09:02:33,159 - WARNING - Received embed with no fields. Skipping.
2025-06-15 09:02:33,159 - ERROR - No holdings were parsed from the embed message.
