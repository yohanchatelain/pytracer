import os

from pytracer.utils.singleton import Singleton


class ContextManager(Singleton):

    def __init__(self, env=None, exclude=None):
        """

        Parameters
        ----------
        env : dict, default: None
            dict of environment variables and values to export
        exclude : list of str, default: None
            list of environment variables to exclude (unset)
        """
        self._include_env = env
        self._exclude_env = exclude
        self._contexts = {}

    def _save_contexts(self):
        if self._include_env is not None:
            for env in self._include_env.keys():
                self._contexts[env] = os.getenv(env)
        if self._exclude_env is not None:
            for env in self._exclude_env:
                self._contexts[env] = os.getenv(env)

    def _set_contexts(self):
        for env, value in self._include_env.items():
            os.environ[env] = value
        for env in self._exclude_env:
            if env in os.environ:
                os.environ.pop(env)

    def _restore_context(self):
        if self._include_env is not None:
            for env in self._include_env.keys():
                if value := self._contexts[env]:
                    os.environ[env] = self._contexts[env]
                else:  # value is None, it didn't exist before, so we remove it
                    os.environ.pop(env)
        if self._exclude_env is not None:
            for env in self._exclude_env:
                if value := self._contexts[env]:  # It existed before
                    os.environ[env] = value
                # else it didn't exist before

    def __enter__(self):
        self._save_contexts()
        self._set_contexts()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._restore_context()
