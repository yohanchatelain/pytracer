

def trace(file, bash, kwargs='', expect_failure=False):
    bash.auto_return_code_error = True
    bash.run_script("pytracer", ["trace", f"--command {file} {kwargs}"])
    def check(x, y): return x != y if expect_failure else x == y
    print(bash.last_return_code, 0, check(bash.last_return_code, 0))
    assert(check(bash.last_return_code, 0))
