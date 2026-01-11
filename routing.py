class _StaticTrie:
    def __init__(self):
        self.root = {"h": None, "c": {}}

    def add(self, prefix, handler):
        node = self.root
        for part in self._parts(prefix):
            children = node["c"]
            if part not in children:
                children[part] = {"h": None, "c": {}}
            node = children[part]
        node["h"] = handler

    def match(self, path):
        node = self.root
        last_handler = None
        for part in self._parts(path):
            children = node.get("c")
            if part not in children:
                break
            node = children[part]
            if node.get("h"):
                last_handler = node["h"]
        return last_handler

    def _parts(self, path):
        if not path or path == "/":
            return []
        if path[0] == "/":
            path = path[1:]
        if path.endswith("/"):
            path = path[:-1]
        return path.split("/") if path else []


class _RouteTrie:
    def __init__(self):
        self.root = {"h": None, "c": {}, "p": None, "pn": None}

    def add(self, pattern, handler):
        node = self.root
        for part in self._parts(pattern):
            if part.startswith("<") and part.endswith(">"):
                param_name = part[1:-1]
                if node.get("p") is None:
                    node["p"] = {"h": None, "c": {}, "p": None, "pn": None}
                node["pn"] = param_name
                node = node["p"]
            else:
                children = node["c"]
                if part not in children:
                    children[part] = {"h": None, "c": {}, "p": None, "pn": None}
                node = children[part]
        node["h"] = handler

    def match(self, path):
        node = self.root
        params = {}
        for part in self._parts(path):
            children = node.get("c")
            if part in children:
                node = children[part]
            elif node.get("p") is not None:
                param_name = node.get("pn")
                if param_name is not None:
                    params[param_name] = part
                node = node["p"]
            else:
                return None
        if node.get("h"):
            return node["h"], params
        return None

    def _parts(self, path):
        if not path or path == "/":
            return []
        if path[0] == "/":
            path = path[1:]
        if path.endswith("/"):
            path = path[:-1]
        return path.split("/") if path else []


class Router:
    def __init__(self):
        self.route_map = {}
        self.static_routes = []
        self._static_trie = _StaticTrie()
        self._dyn_tries = {}
        self._not_found_cache = set()

    def add(self, method, path, handler):
        if "<" in path and ">" in path:
            trie = self._dyn_tries.get(method)
            if trie is None:
                trie = _RouteTrie()
                self._dyn_tries[method] = trie
            trie.add(path, handler)
        else:
            self.route_map[(method, path)] = handler

    def add_static(self, url_path, handler):
        self.static_routes.append((url_path, handler))
        self._static_trie.add(url_path, handler)

    def match(self, method, path):
        # 1. Exact match
        handler = self.route_map.get((method, path))
        params = {}
        
        if handler:
            return handler, params

        # 2. Check 404 cache
        if path in self._not_found_cache:
            return None, None

        # 3. Static match
        handler = self._static_trie.match(path)
        if handler:
            return handler, params

        # 4. Dynamic match
        trie = self._dyn_tries.get(method)
        if trie is not None:
            matched = trie.match(path)
            if matched is not None:
                handler, params = matched
                return handler, params

        # 5. Not found
        self._not_found_cache.add(path)
        return None, None
