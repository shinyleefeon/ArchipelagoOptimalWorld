import zlib
import pickle
import sys
import os
import pprint
import io

class PlaceholderObject:
    """
    A base class for dynamically created placeholders.
    It captures initialization arguments and state so you can see the data
    even if the original source code class is missing.
    """
    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
        self._state = None

    def __repr__(self):
        cls = self.__class__
        state_repr = ""
        if self._state:
            # simplify state display if it's large
            state_repr = f" state={str(self._state)[:100]}..." if len(str(self._state)) > 100 else f" state={self._state!r}"
        
        args_repr = ""
        if self._args:
            args_repr = f" args={self._args!r}"

        return f"<{cls.__module__}.{cls.__name__}{args_repr}{state_repr}>"
    
    def __setstate__(self, state):
        self._state = state

class SafeUnpickler(pickle.Unpickler):
    """
    A custom unpickler that handles missing classes by generating
    dynamic replacement classes on the fly.
    """
    def __init__(self, file, **kwargs):
        super().__init__(file, **kwargs)
        self.known_placeholders = {}

    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except (ImportError, AttributeError):
            key = (module, name)
            if key not in self.known_placeholders:
                # Create the dynamic class with the correct name and module
                # This satisfies the NEWOBJ opcode requirement.
                new_class = type(name, (PlaceholderObject,), {
                    "__module__": module,
                    "__doc__": f"Dynamic placeholder for {module}.{name}"
                })
                self.known_placeholders[key] = new_class
            
            return self.known_placeholders[key]

def decode_file(input_path):
    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        return

    print(f"Processing {input_path}...")

    try:
        with open(input_path, 'rb') as f:
            raw_data = f.read()

        if not raw_data:
             print("Error: File is empty.")
             return

        # Step 1: Check Format Version (First Byte)
        format_version = raw_data[0]
        print(f"Format Version: {format_version}")

        # Step 2: Decompress (Zlib)
        try:
            # MultiServer.py skips the first byte (version) before decompressing
            decompressed_data = zlib.decompress(raw_data[1:])
        except zlib.error as e:
            print(f"Error: Zlib decompression failed. {e}")
            return

        # --- NEW: Save the raw decompressed file immediately ---
        raw_output_path = input_path + ".raw.pickle"
        try:
            with open(raw_output_path, 'wb') as raw_out:
                raw_out.write(decompressed_data)
            print(f"SUCCESS: Raw decompressed file saved to: {raw_output_path}")
            print("You can use this .pickle file with other tools or scripts.")
        except Exception as e:
            print(f"Warning: Could not write raw pickle file. {e}")
        # -------------------------------------------------------

        # Step 3: Deserialize (Pickle with Custom Unpickler)
        print("Attempting to generate readable text format...")
        try:
            file_buffer = io.BytesIO(decompressed_data)
            unpickler = SafeUnpickler(file_buffer)
            data = unpickler.load()
            
            # Step 4: Write to Text Output File
            text_output_path = input_path + ".decoded.txt"
            with open(text_output_path, 'w', encoding='utf-8') as out_f:
                pprint.pprint(data, stream=out_f, width=120, indent=2)
            print(f"SUCCESS: Readable text dump saved to: {text_output_path}")

        except Exception as e:
            print(f"\nWarning: Could not generate readable text dump due to object complexity.")
            print(f"Error details: {e}")
            print(f"However, the raw file '{raw_output_path}' was generated successfully.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python decode_archipelago.py <path_to_file.archipelago>")
        print("You can also drag and drop the file onto this script.")
        input("Press Enter to exit...")
    else:
        file_path = sys.argv[1]
        decode_file(file_path)