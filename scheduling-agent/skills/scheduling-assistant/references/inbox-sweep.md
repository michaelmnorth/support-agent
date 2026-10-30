# Inbox sweep: the scheduled-task prompt

Use this as the prompt of a Claude Code cloud scheduled task (claude.ai/code/routines) or a Cowork scheduled
task, running every 15 to 30 minutes on weekdays with the Microsoft 365 connector attached and the
`scheduling-assistant` skill enabled. It is the closest thing to "triggered by a new email" that exists today.

```
Run the scheduling-assistant skill in sweep mode.

1. In Outlook, list unread messages received in the last 2 hours that are NOT already in category
   "Scheduled by assistant". Also list messages in any thread recorded as `proposed` in
   clients/*/scheduling-log.md that have a newer reply.
2. For each message, decide: (a) a new scheduling request, (b) a reply picking one of our proposed times,
   (c) a counter-proposal, or (d) unrelated. Skip (d) silently.
3. For (a): follow workflow A. For (b) and (c): follow workflow B/C.
4. Respect each client's `automation` setting. For anything that needs my approval, create the Outlook draft
   in the thread and send me ONE Teams chat message (to myself) summarizing every pending item, using the
   owner-ping format. Do not email me.
5. Never send to a contact that is not in clients/. Never create an invite for a time that check_time rejects.
6. Finish with a one-paragraph summary: handled, awaiting my approval, skipped.
```

Notes

- The task runs under the creator's identity and uses their own connectors. Each teammate creates their own.
- Rate: 15 minutes is a sensible cadence. A client replying "yes" waits at most that long for the invite.
- Approval round trip: the owner replies to the Teams ping; the **next** sweep sees the approval and sends.
  If that is too slow, run the skill interactively ("send the Acme draft") instead of waiting.
- Marking processed: category `Scheduled by assistant` is the idempotency marker. If the connector cannot set
  categories, fall back to the log file: a thread id listed in `scheduling-log.md` with status `proposed` or
  `booked` is already handled.
