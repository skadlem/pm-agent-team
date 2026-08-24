def redeem(token):
    with db.transaction():
        row = db.get(token)
        if row.redeemed:
            raise ReplayError(token)
        db.mark_redeemed(token)
