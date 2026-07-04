from ptcg_runtime.runtime import get_runtime

RUNTIME = get_runtime()


def agent(obs_dict: dict) -> list[int]:
    return RUNTIME.act(obs_dict)
