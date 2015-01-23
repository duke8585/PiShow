import locale
import os
import sys
import time

from dropbox import client, session

class DropboxConnector:
    TOKEN_FILE = "token_store.txt"

    def __init__(self, local_path, db_path):
        """
        Parameters:
            local_path: The directory in which to store images on the Pi
            db_path: The remote directory located on the Dropbox account
        Returns: n/a
        """
        self.current_path = db_path
        self.local_directory = local_path

        self.api_client = None
        try:
            serialized_token = open(self.TOKEN_FILE).read()
            if serialized_token.startswith('oauth1:'):
                #access_key, access_secret = serialized_token[len('oauth1:'):].split(':', 1)
                #sess = session.DropboxSession(self.app_key, self.app_secret)
                #sess.set_token(access_key, access_secret)
                #self.api_client = client.DropboxClient(sess)
                #print "[loaded OAuth 1 access token]"
                print "OAuth1 not supported."
                sys.exit()
            elif serialized_token.startswith('oauth2:'):
                access_token = serialized_token[len('oauth2:'):]
                self.api_client = client.DropboxClient(access_token)
                print "[loaded OAuth 2 access token]"
            else:
                print "Malformed access token in %r." % (self.TOKEN_FILE,)
        except IOError:
            print "Not authorized. Use auth.sh to authenticate."

    @classmethod
    def do_login(cls):
        """
        Log in to a Dropbox account

        Parameters: n/a
        Returns: n/a
        """
        key_file = None
        try:
	       key_file = open("app_key.txt", "r")
        except IOError:
            print "No app_key.txt. Exiting."
            sys.exit()
        keys = key_file.readlines()
        app_key = keys[0].strip()
        app_secret = keys[1].strip()
        flow = client.DropboxOAuth2FlowNoRedirect(app_key, app_secret)
        authorize_url = flow.start()
        sys.stdout.write("1. Go to: " + authorize_url + "\n")
        sys.stdout.write("2. Click \"Allow\" (you might have to log in first).\n")
        sys.stdout.write("3. Copy the authorization code.\n")
        code = raw_input("Enter the authorization code here: ").strip()

        try:
            access_token, user_id = flow.finish(code)
        except rest.ErrorResponse, e:
            sys.stdout.write('Error: %s\n' % str(e))
            return

        with open(self.TOKEN_FILE, 'w') as f:
            f.write('oauth2:' + access_token)
        #self.api_client = client.DropboxClient(access_token)

    def get_file_list(self, directory):
        """
        Gets a list of files in a Dropbox directory.

        Parameters:
            directory: The directory in which to get the filelist.
        Returns: A filelist if it is found, otherwise None.
        Raises: dropbox.rest.ErrorResponse
        """
        resp = self.api_client.metadata(directory)

        if 'contents' in resp:
            files = []
            for f in resp['contents']:
                name = os.path.basename(f['path'])
                encoding = locale.getdefaultlocale()[1] or 'ascii'
                files.append(('%s' % name).encode(encoding))
            return files
        else:
            return None

    def get_file(self, filename):
        """
        Gets a file from the current Dropbox directory.

        Parameters:
            filename: The name of the desired file.
        Returns: The file
        Raises: dropbox.rest.ErrorResponse
        """
        to_file = None
        try:
            to_file = open(os.path.expanduser(self.local_directory + filename), "wb")
        except IOError:
            print self.local_directory + " is missing!"
            return

        f, metadata = self.api_client.get_file_and_metadata(self.current_path + "/" + filename)
        to_file.write(f.read())
        
    def get_metadata(self, filename):
        """
        Gets a file's metadata from the current Dropbox directory.

        Parameters:
            filename: The name of the desired file.
        Returns: The file's metadata
        Raises: dropbox.rest.ErrorResponse
        """
        f, metadata = self.api_client.get_file_and_metadata(self.current_path + "/" + filename)
        return metadata

    def poll(self, path):
        had_changes = False
        cursor = None
        result = self.api_client.delta(cursor, path)
        cursor = result['cursor']
        if result['reset']:
            print 'RESET'

        if len(result['entries'] > 0):
            had_changes = True

        for path, metadata in result['entries']:
            if metadata is not None:
                print '%s was created/updated' % path
            else:
                print '%s was deleted' % path

        while result['has_more']:
            result = self.api_client.delta(cursor, path)
            cursor = result['cursor']
            if result['reset']:
                print 'RESET'

            for path, metadata in result['entries']:
                if metadata is not None:
                    print '%s was created/updated' % path
                else:
                    print '%s was deleted' % path

        if had_changes:
            return True

        changes = False
        # poll until there are changes
        while not changes:
            result = self.api_client.longpoll_delta(cursor, 120)

            changes = result['changes']
            if not changes:
                print 'Timeout, polling again...'

            backoff = result['backoff'] if 'backoff' in result else None
            if backoff is not None:
                print 'Backoff requested. Sleeping for %d seconds...' % backoff
                time.sleep(backoff)
                print 'Resuming polling...'

        return self.poll()
