import pickle
import pprint
import os
import sys

# --- Placeholder Object to capture missing class data ---
class PlaceholderObject:
    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
        self._state = None
    
    def __getattr__(self, name):
        # Access _state safely
        state = self.__dict__.get("_state")
        
        # Case 1: State is a simple dictionary
        if isinstance(state, dict) and name in state:
            return state[name]
        
        # Case 2: State is a tuple (common for objects with __slots__)
        # Format is typically (dict_state, slot_state)
        if isinstance(state, tuple) and len(state) == 2:
            dict_state, slot_state = state
            if isinstance(dict_state, dict) and name in dict_state:
                return dict_state[name]
            if isinstance(slot_state, dict) and name in slot_state:
                return slot_state[name]

        raise AttributeError(f"'{self.__class__.__name__}' placeholder has no attribute '{name}'")

    def __repr__(self):
        return f"<{self.__class__.__module__}.{self.__class__.__name__}>"
    
    def __setstate__(self, state):
        self._state = state

class SafeUnpickler(pickle.Unpickler):
    def __init__(self, file, **kwargs):
        super().__init__(file, **kwargs)
        self.known_placeholders = {}
    
    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except (ImportError, AttributeError):
            key = (module, name)
            if key not in self.known_placeholders:
                new_class = type(name, (PlaceholderObject,), {
                    "__module__": module
                })
                self.known_placeholders[key] = new_class
            return self.known_placeholders[key]
# -----------------------------------------------------------------------

def resolve_attribute(obj, attr_name):
    """
    Tries to find an attribute in a PlaceholderObject using various pickle storage methods.
    """
    # 1. Try direct attribute access (via __getattr__)
    try:
        val = getattr(obj, attr_name)
        if val is not None: return val
    except AttributeError:
        pass

    # 2. Check _state directly
    if hasattr(obj, '_state'):
        state = obj._state
        if isinstance(state, dict):
            return state.get(attr_name)
        elif isinstance(state, tuple) and len(state) == 2:
            # Check both parts of the tuple
            if isinstance(state[0], dict) and attr_name in state[0]: return state[0][attr_name]
            if isinstance(state[1], dict) and attr_name in state[1]: return state[1][attr_name]

    # 3. Check _args (Constructor arguments)
    # Sometimes objects like NamedTuples store data in _args.
    # We make a best guess based on order.
    # NetworkSlot usually: (name, game, type, ...)
    if hasattr(obj, '_args') and obj._args and isinstance(obj._args, tuple):
        if attr_name == 'name' and len(obj._args) >= 1: return obj._args[0]
        if attr_name == 'game' and len(obj._args) >= 2: return obj._args[1]

    return None

def extract_readable_spheres(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at path: {file_path}")
        return None

    print(f"Loading: {file_path}")
    try:
        with open(file_path, 'rb') as f:
            data = SafeUnpickler(f).load()
        
        print("Data loaded successfully.")
        
        if 'spheres' not in data:
            print("Error: 'spheres' key not found.")
            return

        # --- 1. Build Location Database ---
        print("Building Location Database...")
        location_db = {} # { 'GameName': { LocationID: 'LocationName' } }
        
        if 'datapackage' in data:
            for game_name, game_data in data['datapackage'].items():
                if 'location_name_to_id' in game_data:
                    name_to_id = game_data['location_name_to_id']
                    id_to_name = {v: k for k, v in name_to_id.items()}
                    location_db[game_name] = id_to_name

        # --- 2. Build Player Database ---
        print("Building Player Database...")
        player_db = {} # { PlayerID: { 'name': 'PlayerName', 'game': 'GameName' } }
        
        if 'slot_info' in data:
            debug_printed = False
            for slot_id, slot_obj in data['slot_info'].items():
                
                p_name = resolve_attribute(slot_obj, 'name')
                p_game = resolve_attribute(slot_obj, 'game')

                # DEBUG: If we fail to find data for the first slot, print the object structure
                if (not p_name or not p_game) and not debug_printed:
                    print("\n[DEBUG] Failed to extract info for a slot. Printing raw object structure:")
                    print(f"Class: {slot_obj.__class__.__module__}.{slot_obj.__class__.__name__}")
                    print(f"_args: {getattr(slot_obj, '_args', 'N/A')}")
                    print(f"_state: {getattr(slot_obj, '_state', 'N/A')}")
                    print("[DEBUG] End object structure\n")
                    debug_printed = True

                if not p_name: p_name = f"Unknown Player {slot_id}"
                if not p_game: p_game = "Unknown Game"

                player_db[slot_id] = {'name': p_name, 'game': p_game}

        # --- 3. Generate Readable Report ---
        spheres_data = data['spheres']
        base_name = os.path.splitext(file_path)[0]
        output_file = f"{base_name}_spheres_readable.txt"
        
        print(f"Translating {len(spheres_data)} spheres...")

        with open(output_file, "w", encoding="utf-8") as out:
            out.write(f"=== READABLE SPHERES REPORT ===\n")
            out.write(f"Source: {os.path.basename(file_path)}\n")
            out.write(f"Total Spheres: {len(spheres_data)}\n")
            out.write("="*60 + "\n\n")

            for i, sphere in enumerate(spheres_data):
                out.write(f"--- Sphere {i + 1} ---\n")
                if not sphere:
                    out.write("  (Empty Sphere)\n")
                    continue

                # Sort by player ID for consistency
                for player_id in sorted(sphere.keys()):
                    location_ids = sphere[player_id]
                    
                    p_info = player_db.get(player_id, {'name': f"Player {player_id}", 'game': 'Unknown'})
                    p_name = p_info['name']
                    p_game = p_info['game']
                    
                    out.write(f"  Player: {p_name} ({p_game})\n")
                    
                    loc_map = location_db.get(p_game, {})
                    
                    # Sort locations by ID
                    for loc_id in sorted(location_ids):
                        loc_name = loc_map.get(loc_id, f"Unknown ID {loc_id}")
                        out.write(f"    - {loc_name}\n")
                    
                    out.write("\n")
                out.write("\n")

        print(f"SUCCESS: Readable report written to: {output_file}")

    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python read_pickle.py <path_to_file.raw.pickle>")
        input("Press Enter to exit...")
    else:
        file_path = sys.argv[1]
        extract_readable_spheres(file_path)
        input("\nPress Enter to close...")