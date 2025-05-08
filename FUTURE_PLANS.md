# Future Features & Design Notes

This file is a repo-root note to track future plans, design choices, and feature refinments within the RSAssistant project.

- There are 3 active channels:
    - **Order handling channel**: where orders are submitted and confirmation messages are processed.
    - **Nasdaq feed channel**: incoming corporate actions are live updated.
    - **Research/watchlist channel**: bot breaks out the news from the Nasdap announcements, and spots fractional share events with share roundup.


## Current message handling flow

The main loop for message routing within RSAssistant proceeds as follows:

### Step 1: On message call enters "RSAssistant.py"
- The method `on message` is called when the bot receives a new message event.
- It’s dispatched to the appropriate handler based on the message's channel.


### Step 2: Channel withouts
- If channel = Secondary: `utils/on_message_utils.handle_secondary_channel(message.bot, message)`
- If channel = Primary: `alert_channel_message()` with return to announcement feed orders with confirmation flow
  - May route through `reverses_confirmed` from return value of `alert_channel_message()`
  - Trigger posting to channel if applicable: `channel.send()`

  - Else, we default to `utils/on_message_utils/handle_secondary_channel ` to process the message.


### Step 3: Final action within util modules
- After the message is parsed, an order may be submitted, a log may initiate, or an announcement may be generated.
  - These actions are carried out via utils like `order_exec.py`, `order_queue_manager.py`, etc.

  - Flow typically terminates with communication with an external Rest api response, or sends the order to a relevant service.

- Message handling is therefore the heart of all channel-based interactions in RSAssistant.
