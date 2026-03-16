OPT_OUT_CACHE_KEY = "opt_out:{server_id}:{user_id}"


def invalidate_opt_out_cache(cache, server_id: int, user_id: int) -> None:
    if cache:
        cache.delete(OPT_OUT_CACHE_KEY.format(server_id=server_id, user_id=user_id))
