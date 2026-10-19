# Parity Guide

This synthetic guide exists only for ingestion parity tests. It describes a
small lending library that tracks books, members, and loans.

## Members

Each member has a card number and a home branch. A member can borrow up to
five books at one time. Overdue loans block new loans until the member
returns the overdue items.

## Loans

A loan starts when the desk scans the book and the card. The default loan
period is fourteen days. Members can renew a loan twice if no other member
has reserved the book.

### Reservations

A reservation holds a returned book at the desk for three days. The system
sends one notice when the book arrives and one reminder on the last day.
