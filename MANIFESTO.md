# Manifesto

*Українською: [MANIFESTO.uk.md](MANIFESTO.uk.md)*

**Nobody should stand in front of a doctor without their own history.**

## Who this is for

A daughter who takes her mother from doctor to doctor with a folder of papers. Some are from
another country, some in another language, some are lost. Every new doctor starts from zero,
and the one thing her mother wanted to say gets forgotten in the corridor.

This project exists for her. Everything below is what we believe, what already works, and what
is still only an intention.

## What we believe

1. **Your medical history is yours.** Not the hospital's, not the insurer's, not a chatbot's,
   and not ours. It lives with you. Others hold copies, with your permission.
2. **Nothing becomes a fact until you say "yes, this is true."** A machine may read a lab
   report. Only a person confirms it.
3. **The measure is what happened next.** A memory nobody acts on is an archive. We judge
   ourselves by whether the important thing reached a doctor, and whether someone checked what
   came of it.
4. **Your own words come first.** Before any number: what you want the doctor to hear.
5. **We collect quietly and speak rarely.** No reminders for the sake of reminders. Silence
   never means "everything is fine": the program sees only what was entered into it.
6. **The AI assistant is a guest.** You can replace it. The history stays home.
7. **Safety rules are code anyone can read.** Critical values and red flags are decided by
   deterministic rules, not by a model's mood.
8. **We lead to the doctor, never away.** This is not a doctor, not a diagnosis, and not a
   reason to delay care. It does not change doses and does not judge drug combinations.
9. **If computers are not your thing, that is not your fault.** Someone should sit down next to
   you. Whoever helps you put your history together does not take it away with them.
10. **We count our mistakes out loud.**

## What is true today

- Your records live in a database on your own machine. health-os itself sends nothing anywhere.
- Lab values are staged as *pending* and count only after you approve them.
- Critical values, red flags, the crisis response and the refusal to assess drug interactions
  are code, independent of the model. The assistant is told never to say "everything is normal".
- It works with any MCP client, including fully local models.
- It can prepare a brief before a doctor's visit and list results that nobody has followed up.
- The source is open under AGPL-3.0.

## What is not true yet

We would rather say this ourselves.

- **No doctor has been asked yet whether they would read it.** Until one has, "the doctor
  trusts it" is a hope, not a claim.
- **It is not for everyone yet.** Today you need Docker and someone technical nearby.
- **"Local" is not the same as "safe".** The database is not encrypted at rest; encrypt your
  disk. A lost laptop or a lost sheet of paper is still a leak.
- **There is no one-page sheet in the doctor's language, no open export format, and no mode
  for a helper working on someone else's device.** These are intentions.
- **It has one author, and a CLA in his name.** "It will outlive its author" is not a fact
  until the format and the dictionary can live without him.
- **Nobody has measured whether this saves lives or lowers anyone's blood pressure.** We
  intend to measure it and to publish the result either way.

## Where we are going

In this order, and each step only if the previous one held up in front of real people.

1. **One sheet.** Your history on one page, in the language of the doctor you are going to.
   First line: your own words. Then medications, allergies, diagnoses, the few numbers that
   matter, each with its date and source. Marked plainly: compiled from the patient's papers,
   not a medical document, check what matters against the originals.
2. **A helper beside you.** A daughter, a volunteer, a pharmacist, who can sort someone's
   folder in an hour. They work on that person's device or on paper, and leave with nothing.
3. **A closed loop.** A worrying number is not an alert. It is something that stays open until
   it has been shown to a doctor and someone has checked what happened. We start with home
   blood pressure, because there the benefit is established.
4. **A dictionary that belongs to no one.** Drug brand names and lab test names across
   languages, in its own repository, editable by pharmacists and translators who do not write
   code.
5. **The right to the original.** One day a lab hands the result straight to you in an open
   format, and a doctor in any country can read it. In the EU you already have the right to a
   copy of your data. What is missing is somewhere for it to arrive.

## What you can do today

Sit down with one person for an hour. Sort their folder. On a single sheet write their
medications, allergies, diagnoses, and one sentence in their own words: what they want the
doctor to hear. A pen is enough. No software required.

If you can run software, do the same with health-os for someone who cannot, and tell us every
place you got stuck. If you are a doctor, nurse or pharmacist, take a printed sheet and a pen,
and cross out everything you would not read. That is the most valuable contribution this
project can receive right now.

---

*Your history is in your hands, and we tell you honestly where we may be wrong.*
