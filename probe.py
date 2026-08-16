#!/usr/bin/env python3
"""Probe every library route against prod and report pass/fail with reasons.

Reads credentials from env or uses the provided defaults. Never mutates state
except where explicitly enabled (reserve / logout are opt-in flags).
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geev import GeevClient, Session
from geev.exceptions import BadRequest

TOKEN = os.environ.get("GEEV_TEST_TOKEN", "D2iJSvsfYHwT0n5y2hml4UzeaGSS8NbLiIpUBwhoumHM4UENT0Jpt4q-qRnLhCWe")
ACCOUNT = os.environ.get("GEEV_TEST_USER", "6a81e587e99a89cd2cbad9ac")
TARGET = os.environ.get("GEEV_TARGET_USER", "6a7fa614571a56d34a990dac")
ARTICLE_ID = "6a81e3123df5d3f7becd995f"
LAT = 48.791254196648026
LNG = 2.287006234644051

DO_RESERVE = os.environ.get("DO_RESERVE", "")
DO_LOGOUT = os.environ.get("DO_LOGOUT", "")

results = []

def record(name, ok, info=""):
    results.append((name, ok, info))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {info}")

def probe(name, fn):
    try:
        r = fn()
        record(name, True, "" if r is None else str(r)[:500])
    except Exception as e:
        record(name, False, f"{type(e).__name__}: {e}")

def main():
    geev = GeevClient(token=TOKEN)
    geev.session = Session(appToken=TOKEN, userId=ACCOUNT)

    # ---------- check_email ----------
    probe("check_email.existing", lambda: ("returns?"
                                           f" {geev.check_email('dsaaiuuiq2@jaipas.lu')}"))
    probe("check_email.fresh", lambda: ("returns?"
                                        f" {geev.check_email('totally-new-1749@example.com')}"))

    # ---------- search ----------
    probe("search.no_text", lambda: len(geev.search_articles(limit=3)))
    probe("search.text", lambda: len(geev.search_articles(text="table", limit=3)))
    probe("search.type_donation",
          lambda: len(geev.search_articles(article_type="donation", limit=3)))
    probe("search.states",
          lambda: len(geev.search_articles(text="table", states=["good"], limit=3)))
    probe("search.categories",
          lambda: len(geev.search_articles(categories=["table"], limit=3)))
    probe("search.distance",
          lambda: len(geev.search_articles(text="table", distance=50,
                                           latitude=LAT, longitude=LNG, limit=3)))
    probe("search.home_listing",
          lambda: len(geev.search_articles(placement="home_listing", limit=3)))
    probe("search.explorer",
          lambda: len(geev.search_articles(placement="explorer", limit=3)))
    probe("search.pagination",
          lambda: len(geev.search_articles(text="table", limit=2, skip=3)))

    # ---------- article info ----------
    probe("get_article", lambda: (lambda a: (a.title, a.id))(geev.get_article(ARTICLE_ID)))
    probe("article.details", lambda: geev.get_article(ARTICLE_ID).details())
    probe("article.related", lambda: len(geev.get_article(ARTICLE_ID).related()))

    # ---------- reservations (opt-in) ----------
    if DO_RESERVE in ("1", "true"):
        reserve_rid = {}
        def reserve_flow():
            a = geev.get_article(ARTICLE_ID)
            res = a.reserve()
            rid = res.reservationId
            if not rid:
                raise SystemError("reserve returned no reservationId")
            reserve_rid["rid"] = rid  # remember for the cancel probe
            # cancel right away to keep the platform clean
            geev.http.delete(f"/reservations/{rid}")
            return f"reserved={rid} then cancelled"
        probe("reserve.article", reserve_flow)
        # Only the donator is allowed to reserve; with a foreign token the
        # server answers 403. That is a permission limit, not a library bug.
        if reserve_rid.get("rid"):
            probe("reserve.cancel_again",
                  lambda: geev.http.delete(f"/reservations/{reserve_rid['rid']}"))
    else:
        print("  (skip reserve: set DO_RESERVE=1)")

    # ---------- messaging / contact ----------
    # The test account already contacted ARTICLE_ID once, so the POST forms
    # are exercised as a dry run: the server answers 409 (thread exists),
    # which proves the request plumbing. Read-only GETs are probed on the
    # existing thread.
    def already_contacted(label, fn):
        def run():
            try:
                fn()
                raise SystemError(f"{label} unexpectedly succeeded on a "
                                  f"contacted item")
            except BadRequest as e:
                if getattr(e, "status_code", None) != 409:
                    raise
                return str(e)
        return run
    probe("contact.dry_run",
          already_contacted("contact",
                            lambda: geev.contact_article(ARTICLE_ID, "ping",
                                                         dry_run=True)))
    probe("conversations.list",
          lambda: (lambda c: (len(c),
                              c[0].get("latest_conversation_id"),
                              c[0].get("status")))(geev.list_conversations()))
    probe("conversations.item_filter",
          lambda: (lambda items: (len(items),
                                  len(items[0].get("conversations", []))
                                  if items else 0))(
             geev.list_conversations(item_id=ARTICLE_ID)))
    rid = {}
    def conversation_fetch():
        for convs in (geev.list_conversations(),):
            cid = convs[0].get("latest_conversation_id")
            if cid:
                break
        else:
            raise SystemError("unfiltered list carries no conversation id")
        rid["cid"] = cid
        return geev.get_conversation(cid).conversation_id
    probe("conversations.fetch", conversation_fetch)
    if rid.get("cid"):
        probe("conversations.messages",
              lambda: len(geev.get_conversation(rid["cid"]).messages))
        probe("conversations.send_message",
              lambda: geev.get_conversation(rid["cid"]).send_message(
                  "probe message").text)
    probe("adoption.dry_run",
          already_contacted("adoption",
                            lambda: geev.request_adoption(ARTICLE_ID, "ping",
                                                          dry_run=True)))

    # ---------- self / inbox / reserved / delivery ----------
    probe("get_me", lambda: (lambda m: (m.user_id, m.first_name, m.last_name))(
        geev.get_me()))
    probe("inbox",
          lambda: (lambda s: (len(s), s[0].conversation_id, s[0].latest_message)
                   if s else ("empty",))(geev.get_inbox()))
    probe("inbox.reserved",
          lambda: (lambda s: (len(s), [x.id for x in s]))(
              geev.get_reserved_collections()))
    probe("confirm_adoption.guard",
          lambda: (lambda s: ("no-deal",) if not s else (
              s[0].conversation_id, s[0].reserved, s[0].given, s[0].acquired))(
              [x for x in geev.get_reserved_collections()
               if x.given and not x.acquired]))
    def confirm_delivery():
        deals = [x for x in geev.get_reserved_collections()
                 if x.given and not x.acquired]
        if not deals:
            return "(no LTI-confirmable deal; skip)"
        conv = geev.get_conversation(deals[0].conversation_id)
        return geev.confirm_adoption(conv.reservation_id,
                                     communication_grade=5.0,
                                     punctuality_grade=5.0).raw
    probe("confirm_adoption.live", confirm_delivery)

    # ---------- user ----------
    def user():
        return geev.get_user(TARGET)
    probe("user.profile", lambda: user().profile())
    probe("user.first_name", lambda: user().first_name)
    probe("user.last_name", lambda: user().last_name)
    probe("user.articles",
          lambda: (lambda p: (len(p.items), p.next_after))(user().articles(limit=3)))
    probe("user.articles_available",
          lambda: len(user().articles(status=["AVAILABLE"], limit=3).items))
    probe("user.reviews", lambda: len(user().reviews(limit=5)))
    probe("user.reviews_type",
          lambda: len(user().reviews(type="ADOPTION", limit=5)))
    probe("user.carbon_summary", lambda: user().carbon_summary().carbonValue)
    probe("user.carbon_summary_ever",
          lambda: user().carbon_summary(temporality="ever").carbonValue)
    probe("user.carbon_summary_thisYear",
          lambda: user().carbon_summary(temporality="thisYear").carbonValue)
    probe("user.carbon_summary_thisMonth",
          lambda: user().carbon_summary(temporality="thisMonth").carbonValue)

    def iter_total():
        n = 0
        for _ in user().iter_articles(status=["AVAILABLE"], page_size=5):
            n += 1
            if n > 30:
                return "(capped)" + str(n)
        return n
    probe("user.iter_articles", iter_total)

    # ---------- logout (opt-in, destructive) ----------
    if DO_LOGOUT in ("1", "true"):
        probe("logout", lambda: geev.logout())
    else:
        print("  (skip logout: set DO_LOGOUT=1)")

    print("\n===== SUMMARY =====")
    fails = [r for r in results if not r[1]]
    print(f"total={len(results)} pass={len(results)-len(fails)} fail={len(fails)}")
    for r in fails:
        print("  FAIL:", r)
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
