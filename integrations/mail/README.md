# Optional official restock email relay

This is not a live stock tracker or a workaround for blocked store requests. It relays store-provided restock notification email subjects to the existing private Telegram chat. It does not fetch products, infer size availability, or track prices. No external server, card, domain or external scraping provider is required. Google Apps Script quotas and scheduling delays apply. No deployment or access to the user's mailbox has occurred.

## Setup (only after receiving a genuine example)

Use a dedicated personal Gmail account if possible. In the store's normal interface, request its own restock notification for a specific item and size, where offered. Verify the actual sender and subject from a genuine received example before configuring any filter. Never guess a sender or include order confirmations, passwords, receipts or unrelated mail.

1. Create a Gmail label named avail-stock. Create a narrow filter for verified stock notification senders AND the specific stock notification subject pattern, using the real received sample. Apply this label only to restock emails. Avoid conversation threads containing unrelated messages.
2. Create a standalone project at https://script.google.com/ and copy Code.gs into the editor.
3. In Project settings > Script properties set BOT_TOKEN, CHAT_ID (the owner's private chat), MAIL_LABEL (avail-stock), ALLOWED_SENDERS (comma-separated exact verified email addresses). Do not put credentials in public repository code.
4. Run testRelay, approve Google's permissions, and verify receipt of the clearly marked test message. Apps Script Gmail permission is broad; use a dedicated personal mailbox and review the consent screen.
5. Run installRelay once to enable its one-minute scheduled check. stopRelay stops it. No Telegram getUpdates or webhook is used, so it can coexist with the original bot.

Only message subjects are forwarded, in plain text. The relay does not send message bodies or links, modify read state, or delete emails. The sender check is not cryptographic authentication; verify the actual message in Gmail, and treat the Telegram notification only as a prompt to open the official shop. The label and exact sender are required. Old emails from before activation are excluded. Up to 100 recent threads and 20 messages per invocation are handled; a failure after send and before saving the message ID can result in a duplicate. Delays and quotas may cause missed messages. Actual store email timing remains unverified and can be slower than stock polling.

References:
- https://www.bershka.com/ww/shopping-guide.html?section=eticket
- https://developers.google.com/apps-script/guides/triggers/installable
- https://developers.google.com/apps-script/guides/services/quotas
