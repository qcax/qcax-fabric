from common import *
def post_publish_state(snapshot,replay_status):
 r=snapshot.get("release",{})
 if r.get("draft") is False and r.get("immutable") is True and replay_status=="FAIL": return "GITHUB_PUBLISHED_REPLAY_FAILED"
 if r.get("draft") is False and r.get("immutable") is True and replay_status=="PASS": return "GITHUB_PUBLISHED_REPLAY_PASS"
 return "GITHUB_POSTVERIFY_INCOMPLETE"
def mutate_with_required_reread(mutate,reread,classify): return attempt_then_reconcile(mutate,reread,classify)
if __name__=="__main__": raise ReleaseError("live GitHub publication is W9 and requires explicit authorization")
