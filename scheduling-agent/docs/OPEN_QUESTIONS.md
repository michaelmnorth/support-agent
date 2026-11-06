# Questions for Michael

Answers change the configuration, not the architecture, so nothing here blocks phase 1. Defaults I used are in
parentheses.

## Your rules
1. Working hours per weekday, and are Fridays different? (Mon–Thu 9–5, Fri 9–4 ET)
2. Lunch block to protect? (12–1 ET)
3. Minimum notice before a meeting an automated reply may offer? (24 hours)
4. Do tentative holds count as busy for the buffer rule? (yes)
5. Max options per proposal, max per day? (4 total, 2 per day, at least 2 hours apart)
6. Any standing no-meeting blocks (focus time) that are not on the calendar as events?

## Your voice
7. Paste two or three real scheduling replies you have sent (email) and one Slack reply. I will turn them into
   `templates/*.txt`. The current wording is my guess at "short and warm".
8. Sign-off: "Thanks, Michael"? Full signature block?
9. Do you want the client's zone first or yours first in the time lines? (client first, yours in parentheses)

## Clients and folders
10. Where do your client folders live in the work instance (local path, Cowork folder, SharePoint)? The loader
    reads `clients/<Folder>/client.yaml`; I can match any convention.
11. Is there an existing file in each folder that already names the customer and contacts (a kickoff doc,
    a Rocketlane export)? I can seed `client.yaml` from it.
12. Which 2 or 3 clients would you trust first with `auto_send`?

## Channels
13. Are your Slack scheduling conversations in Slack Connect channels with the client, internal channels, or
    DMs? This decides whether Claude Tag is acceptable (it posts as "Claude").
14. Is it acceptable for clients to know an assistant drafts the scheduling emails, or must every message read
    as you? (The templates are written as you.)
15. Internal requests (colleagues) versus client requests: same rules, or looser internally (shorter lead time,
    no buffer)?

## Admin and IT
16. Is Microsoft 365 connector **write** access already enabled in your Claude org, or only read? Who is the
    Claude org Owner and the Entra admin to ask?
17. Can you register an Entra app yourself, or is that locked down? (Only matters for the fully local path.)
18. Does your Slack Enterprise Grid require admin approval for custom apps? (Only matters if Slack must be
    first class.)
19. Do you have a Power Automate Premium license, or just the M365-seeded one? (Decides whether phase 5 is
    cheap.)

## Scope
20. Should the assistant also handle *rescheduling* and *cancellations* ("can we push to Thursday")? Not built
    yet; the Graph provider already has the update/cancel endpoints noted.
21. Group scheduling (3+ external people, find a time for all)? Graph `findMeetingTimes` could do this with
    internal attendees; external attendees' free/busy is invisible.
22. Should booked meetings get a prep note in the client folder (agenda stub, last recap link)?
