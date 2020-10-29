import inspect
from functools import wraps
from types import LambdaType, FunctionType, ModuleType


def special_case(module, attr_obj):
    """ Handle special case for module when the object is not
    recognize by the module inspect (ex: numpy.ufunc functions)
    """
    if module.__name__ == "numpy":
        if type(attr_obj).__name__ == "ufunc":
            # if isinstance(attr_obj, ufunc):
            return True
        else:
            return False
    else:
        return False


def wrapper_decorator(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            nb_args = f.__code__.co_argcount
            argnames = f.__code__.co_varnames[:nb_args]
            input_args = [(x, y) for x, y in zip(argnames, args)]
            input_kwargs = [(x, y) for x, y in kwargs.items()]
        except AttributeError:
            input_args = ["x{i}".format(i=i) for i, _ in enumerate(args)]
            input_kwargs = [(x, y) for x, y in kwargs.items()]
        print("{fun} inputs: {args} {kwargs}".format(
            fun=f.__name__,
            args=input_args,
            kwargs=input_kwargs
        ))
        output = f(*args, **kwargs)
        print("{fun} output: {output}".format(
            fun=f.__name__,
            output=output
        ))
        return output
    return wrapper


def wrapper_funcpart(f, *args, **kwargs):
    try:
        nb_args = f.__code__.co_argcount
        argnames = f.__code__.co_varnames[:nb_args]
        input_args = [(x, y) for x, y in zip(argnames, args)]
        input_kwargs = [(x, y) for x, y in kwargs.items()]
    except AttributeError:
        input_args = ["(x{i}, {a})".format(i=i, a=a)
                      for i, a in enumerate(args)]
        input_kwargs = [(x, y) for x, y in kwargs.items()]
    print("{fun} inputs: {args} {kwargs}".format(
        fun=f.__name__,
        args=input_args,
        kwargs=input_kwargs
    ))
    output = f(*args, **kwargs)
    print("{fun} output: {output}".format(
        fun=f.__name__,
        output=output
    ))
    return output


excluded_submodules = {"numpy": ["char"]}
included_submodules = set(["numpy", "numpy.random"])


class Wrapper:

    special_attributes = ["__spec__", "__all__", "__dir__",
                          "__dict__", "__getattr__", "__setattr__",
                          "__hasattr__"]
    sys_modules = dict()

    def __init__(self, module, parent=None):
        self.module = module
        self.parent_module = parent
        self.module_name = self.module.__name__
        self.attributes = dir(self.module)
        self.def_list = ""
        self.sys_modules = dict()
        self.wrapped_module = ModuleType(self.module_name)
        if parent:
            self.wrapped_module.__dict__[
                self.parent_module.__name__] = self.parent_module
        self.wrapped_module.__dict__[self.module_name] = module
        self.wrapped_module.__dict__["wrapper_decorator"] = wrapper_decorator
        self.wrapped_module.__dict__["wrapper_funcpart"] = wrapper_funcpart
        self.real_module = module
        self.definitions = list()
        print("Wrapper class initialized")
        print("Real module", self.real_module)
        print("Populate the wrapped module")
        self.create()

    def get_definitions_list(self):
        return self.def_list

    def get_real_module(self):
        return self.real_module

    def get_wrapped_module(self):
        return self.wrapped_module

    # def getwrapperfunction(self, function, function_wrapper_name):
    #     function_name = function.__name__
    #     wrapper_code = "@wrapper_decorator\ndef {fun_wrp}(*args,**kwargs): return {mod}.{fun}(*args,**kwargs)\n".format(
    #         fun_wrp=function_wrapper_name,
    #         fun=function_name, mod=self.module_name)
    #     print(wrapper_code)
    #     return wrapper_code

    def getwrapperfunction(self, function, function_wrapper_name):
        function_name = function.__name__
        wrapper_code = "def {fun_wrp}(*args,**kwargs): return wrapper_funcpart({mod}.{fun},*args,**kwargs)\n".format(
            fun_wrp=function_wrapper_name,
            fun=function_name, mod=self.module_name)
        print(wrapper_code)
        return wrapper_code

    def getwrapperbasic(self, basic):
        wrapper_code = "{obj} = {mod}.{obj}\n\n".format(
            obj=basic,
            mod=self.module_name)
        return wrapper_code

    def isfunction(self, attr_obj):
        return inspect.isbuiltin(attr_obj) or \
            inspect.isfunction(attr_obj) or \
            inspect.isroutine(attr_obj) or \
            special_case(self.module, attr_obj)

    def islambda(self, function):
        return isinstance(function, LambdaType) and \
            function.__name__ == "<lambda>"

    # Name of the variable that contains the lambda function
    # ex: x = lambda y:y
    def handle_lambda(self, name, function):
        print(inspect.getsource(function))
        lambda_def = inspect.getsource(function) + "\n\n"
        self.def_list += lambda_def
        self.definitions.append(lambda_def)
        code = function.__code__
        func = LambdaType(code, self.wrapped_module.__dict__)
        self.wrapped_module.__dict__[name] = func

    def handle_function(self, name, function):
        function_name = name

        if self.islambda(function):
            self.handle_lambda(name, function)
            return

        if hasattr(function, "__qualname__"):
            function_qualname = function.__qualname__
        else:
            function_qualname = self.module_name + "." + function_name

        #function_fullname_wrapper = function_qualname.replace(".", "_")

        print("Create function {fun}".format(fun=function_name))

        wrapped_fun = self.getwrapperfunction(
            function, function_name)

        self.def_list += wrapped_fun
        self.definitions.append(wrapped_fun)

        code = compile(wrapped_fun, "<string>", "exec")
        func = FunctionType(
            code.co_consts[0], self.wrapped_module.__dict__, function_name)

        self.wrapped_module.__dict__[function_name] = func

    def ismodule(self, attr):
        return inspect.ismodule(attr)

    def handle_module(self, submodule):
        submodule_qualname = submodule.__name__
        submodule_name = submodule.__name__.split(".")[-1]

        if submodule_name in ("math", "python"):
            print("Module", submodule_name, "must be handled correctly")
            return

        print("Submodule detected:", submodule, submodule_name)

        if submodule_qualname in included_submodules:
            print("Submodule {mod} wrapped".format(mod=submodule_name))
            submodule_wrapper = Wrapper(submodule, self.module)
            self.def_list += submodule_wrapper.get_definitions_list()
            self.sys_modules.update(submodule_wrapper.sys_modules)

            submodule_wrp = submodule_wrapper.get_wrapped_module()
            self.wrapped_module.__dict__[submodule_name] = submodule_wrp
        else:
            self.wrapped_module.__dict__[submodule_name] = submodule
        print("wrapped_module.{sub} = {sub}".format(
            sub=submodule_name
        ))
        print("Add submodule {submod}".format(submod=submodule_name))

    def isclass(self, attr):
        return inspect.isclass(attr)

    def handle_class(self, clss):
        pass

    def handle_basic(self, name, obj):
        print("Created object {obj}".format(obj=name))
        self.def_list += self.getwrapperbasic(name)
        self.definitions.append(self.getwrapperbasic(name))
        self.wrapped_module.__dict__[name] = obj

    def isspecialattr(self, attr, attr_obj):
        if attr in self.special_attributes:
            return True
        else:
            return False

    def handle_special(self, attr, attr_obj):
        if attr == "__spec__":
            self.wrapped_module.__spec__ = attr_obj
        elif attr == "__all__":
            self.wrapped_module.__all__ = attr_obj
        elif attr == "__dir__":
            self.wrapped_module.__dir__ = attr_obj
        elif attr == "__dict__":
            self.wrapped_module.__dict__ = attr_obj
        elif attr == "__setattr__":
            self.wrapped_module.__setattr__ = attr_obj
        elif attr == "__getattr__":
            self.wrapped_module.__getattr__ = attr_obj
        elif attr == "__hasattr__":
            self.wrapped_module.__hasattr__ = attr_obj

    def create(self):
        for attr in self.attributes:
            try:
                attr_obj = inspect.getattr_static(self.module, attr)
                print("Get attr", attr)
            except AttributeError:
                print("{} is not handled".format(attr))
                continue
            if self.isspecialattr(attr, attr_obj):
                self.handle_special(attr, attr_obj)
            elif self.isfunction(attr_obj):
                self.handle_function(attr, attr_obj)
            elif self.ismodule(attr_obj):
                self.handle_module(attr_obj)
            elif self.isclass(attr_obj):
                self.handle_class(attr_obj)
            else:
                self.handle_basic(attr, attr_obj)
        return self.def_list

    def define(self, module):
        for submodule in self.submodules:
            setattr(module, submodule.__name__, module)
        for definition in self.definitions:
            exec(definition, module.__dict__)

    def include(self):
        code = ""
        for module_sys_name, module_name in self.sys_modules.items():
            line = 'sys.modules["{sys}"] = globals()["{fun}"]\n'.format(
                sys=module_sys_name,
                fun=module_name
            )
            code += line
        return code
