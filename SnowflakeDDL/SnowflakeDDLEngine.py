"""
AyxPlugin (required) has-a IncomingInterface (optional).
Although defining IncomingInterface is optional, the interface methods are needed if an upstream tool exists.
"""

import AlteryxPythonSDK as Sdk
import xml.etree.ElementTree as Et
import snowflake.connector
import time
import os
import logging

VERSION = '1.0'


class AyxPlugin:
    """
    Implements the plugin interface methods, to be utilized by the Alteryx engine to communicate with a plugin.
    Prefixed with "pi", the Alteryx engine will expect the below five interface methods to be defined.
    """

    def __init__(self, n_tool_id: int, alteryx_engine: object, output_anchor_mgr: object):
        """
        Constructor is called whenever the Alteryx engine wants to instantiate an instance of this plugin.
        :param n_tool_id: The assigned unique identification for a tool instance.
        :param alteryx_engine: Provides an interface into the Alteryx engine.
        :param output_anchor_mgr: A helper that wraps the outgoing connections for a plugin.
        """

        # Default properties
        self.n_tool_id = n_tool_id
        self.alteryx_engine = alteryx_engine

        # Basic lists of text inputs
        self.input_list: list = ['account', 'user', 'password', 'warehouse', 'database', 'schema']

        # Create text box variables
        for item in self.input_list:
            setattr(AyxPlugin, item, None)

        self.auth_type: str = None
        self.okta_url: str = None
        self.temp_dir: str = None
        self.ddl_command: str = None
        self.suspend_wh: bool = False
    
        self.is_initialized: bool = True
        self.single_input = None

    def pi_init(self, str_xml: str):
        """
        Handles input data verification and extracting the user settings for later use.
        Called when the Alteryx engine is ready to provide the tool configuration from the GUI.
        :param str_xml: The raw XML from the GUI.
        """
        # stop workflow is output tools are disbaled in runtime settings
        if self.alteryx_engine.get_init_var(self.n_tool_id, 'DisableAllOutput') == 'True':
            self.is_initialized = False
            return False

        # Getting the user-entered file path string from the GUI, to use as output path.
        root = Et.fromstring(str_xml)

        # Basic text inpiut list
        for item in self.input_list:
            setattr(AyxPlugin, item, root.find(item).text if item in str_xml else None)

        self.auth_type = root.find('auth_type').text  if 'auth_type' in str_xml else None
        self.okta_url = root.find('okta_url').text if 'okta_url' in str_xml else None

       
        self.ddl_command = root.find('ddl_command').text if 'ddl_command' in str_xml else None
        self.suspend_wh = root.find('supend_wh').text == 'True' if 'supend_wh' in str_xml else False


        # fix for listrunner sending line feeds and spaces
        self.okta_url = self.sanitise_inputs(self.okta_url)
        self.ddl_command = self.sanitise_inputs(self.ddl_command)

        # get system temp dir
        self.temp_dir = self.alteryx_engine.get_init_var(self.n_tool_id, "TempPath")

        # check for okta url is using okta
        if self.auth_type == 'okta':
            if not self.okta_url:
                self.display_error_msg(f"Enter a valid Okta URL when authenticating using Okta")
                return False 
            elif 'http' not in self.okta_url:
                self.display_error_msg(f"Supplied Okta URL is not valid")
                return False        

        # Check key is selected
        if not self.ddl_command:
            self.display_error_msg(f"Please select an SQL command field")
            return False

        # data checks
        for item in self.input_list:
            attr = getattr(AyxPlugin, item, None)
            attr = self.sanitise_inputs(attr)
            if attr is None:
                self.display_error_msg(f"Enter a valid {item}")
                return False

        # remove protocol if added
        if '//' in self.account:
            self.account = self.account[self.account.find('//') + 2:]

        # Password field
        self.decrypt_password: str = self.alteryx_engine.decrypt_password(self.password, 0)


    def pi_add_incoming_connection(self, str_type: str, str_name: str) -> object:
        """
        The IncomingInterface objects are instantiated here, one object per incoming connection.
        Called when the Alteryx engine is attempting to add an incoming data connection.
        :param str_type: The name of the input connection anchor, defined in the Config.xml file.
        :param str_name: The name of the wire, defined by the workflow author.
        :return: The IncomingInterface object.
        """

        self.single_input = IncomingInterface(self)
        return self.single_input

    def pi_add_outgoing_connection(self, str_name: str) -> bool:
        """
        Called when the Alteryx engine is attempting to add an outgoing data connection.
        :param str_name: The name of the output connection anchor, defined in the Config.xml file.
        :return: True signifies that the connection is accepted.
        """

        return True

    def pi_push_all_records(self, n_record_limit: int) -> bool:
        """
        Called when a tool has no incoming data connection.
        :param n_record_limit: Set it to <0 for no limit, 0 for no records, and >0 to specify the number of records.
        :return: True for success, False for failure.
        """

        self.display_error_msg('Missing Incoming Connection')
        return False

    def pi_close(self, b_has_errors: bool):
        """
        Called after all records have been processed.
        :param b_has_errors: Set to true to not do the final processing.
        """

        pass

    def sanitise_inputs(self, data: str):
        if data:
            data = None if data.strip() == '' else data
        return data

    def display_error_msg(self, msg_string: str):
        self.alteryx_engine.output_message(self.n_tool_id, Sdk.EngineMessageType.error, msg_string)
        self.is_initialized = False

    def display_info(self, msg_string: str):
        self.alteryx_engine.output_message(self.n_tool_id, Sdk.EngineMessageType.info, msg_string)

    def display_file(self, msg_string: str):
        self.alteryx_engine.output_message(self.n_tool_id, Sdk.Status.file_output, msg_string)


class IncomingInterface:
    """
    This optional class is returned by pi_add_incoming_connection, and it implements the incoming interface methods, to
    be utilized by the Alteryx engine to communicate with a plugin when processing an incoming connection.
    Prefixed with "ii", the Alteryx engine will expect the below four interface methods to be defined.
    """

    def __init__(self, parent: object):
        """
        Constructor for IncomingInterface.
        :param parent: AyxPlugin
        """

        # Default properties
        self.parent = parent

        # Custom membersn
        self.record_info_in = None
        self.field_list: list = []
        self.counter: int = 0
        self.timestamp: int = 0

    def ii_init(self, record_info_in: object) -> bool:
        """
        Handles the storage of the incoming metadata for later use.
        Called to report changes of the incoming connection's record metadata to the Alteryx engine.
        :param record_info_in: A RecordInfo object for the incoming connection's fields.
        :return: True for success, otherwise False.
        """
        field_name: str = ''

        if self.parent.alteryx_engine.get_init_var(self.parent.n_tool_id, 'UpdateOnly') == 'True' or not self.parent.is_initialized:
            return False

        self.parent.display_info(f'Running Snowflake Output version {VERSION}')
        self.record_info_in = record_info_in  # For later reference.

        # # Storing the field names to use when writing data out.
        # for field in range(record_info_in.num_fields):
        #     field_name = record_info_in[field].name
        #     self.field_lists.append([field_name])

        #     self.sql_list[field_name] = (str(record_info_in[field].type), record_info_in[field].size, record_info_in[field].scale)

        self.timestamp = str(int(time.time()))
        self.parent.temp_dir = os.path.join(self.parent.temp_dir, self.timestamp)

        if not os.path.exists(self.parent.temp_dir):
            os.makedirs(self.parent.temp_dir)
        
        # Logging setup
        logging.basicConfig(filename=os.path.join(self.parent.temp_dir, 'snowflake_connector.log'), format='%(asctime)s - %(message)s', level=logging.INFO)

        return True

    def ii_push_record(self, in_record: object) -> bool:
        """
        Responsible for writing the data to csv in chunks.
        Called when an input record is being sent to the plugin.
        :param in_record: The data for the incoming record.
        :return: False if file path string is invalid, otherwise True.
        """

        self.counter += 1  # To keep track for chunking

        if not self.parent.is_initialized:
            return False

        in_value = self.record_info_in[0].get_as_string(in_record)
        if in_value:
            self.field_list.append(in_value)

        # # Storing the string data of in_record
        # for field in range(self.record_info_in.num_fields):
        #     in_value = self.record_info_in[field].get_as_string(in_record)
        #     self.field_lists[field].append(in_value) if in_value is not None else self.field_lists[field].append('NULL')

        # # Writing when chunk mark is met
        # if self.counter % self.cache_size == 0:
        #     self.parent.write_lists_to_csv(self.csv_file, self.field_lists)

        #     # Start new csv file if limit reached
        #     if self.counter % (self.file_size_limit) == 0:
        #         self.file_counter += 1
        #         # create new file name
        #         self.csv_file = self.get_file_name(self.parent.temp_dir, self.parent.table, self.file_counter)

        #         # append headers for new file
        #         for record in range(0, len(self.headers)):
        #             self.field_lists[record].append(self.headers[record])

        return True
      

    def ii_update_progress(self, d_percent: float):
        """
         Called by the upstream tool to report what percentage of records have been pushed.
         :param d_percent: Value between 0.0 and 1.0.
        """

        self.parent.alteryx_engine.output_tool_progress(self.parent.n_tool_id, d_percent)  # Inform the Alteryx engine of the tool's progress

    def ii_close(self):
        """
        Handles writing out any residual data out.
        Called when the incoming connection has finished passing all of its records.
        """
        
        if self.parent.alteryx_engine.get_init_var(self.parent.n_tool_id, 'UpdateOnly') == 'True' or not self.parent.is_initialized:
            return False
        elif self.counter == 0:
            self.parent.display_info('No records to process')
            return False

        con: snowflake.connector.connection = None

        # # Outputting the link message that the file was written
        # if len(self.field_list) > 0 and self.parent.is_initialized:
        #     # First element for each list will always be the field names.
        #     if len(self.field_lists[0]) > 1:
        #         self.parent.write_lists_to_csv(self.csv_file, self.field_lists)

        # # gzip files
        # files = [os.path.join(self.parent.temp_dir, f) for f in os.listdir(self.parent.temp_dir) if self.parent.table in f]

        # #self.parent.gzip(self.csv_file)
        # with concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()*10) as executor:
        #     executor.map(self.parent.gzip, files) 

        # for f in files:
        #     f = os.path.join(self.parent.temp_dir, f)
        #     self.parent.display_file(f'{f} | {f} gzip file is created')

        # # clean key field
        # if self.parent.key:
        #     self.parent.key = cleaner.reserved_words(self.parent.key, self.parent.case_sensitive)

        # # path to gzip files
        # gzip_file = os.path.join(self.parent.temp_dir, self.parent.table).replace('\\', '//')

        # Create Snowflake connection

        try:
            if self.parent.auth_type == 'snowflake':
                con = snowflake.connector.connect(
                                                user=self.parent.user,
                                                password=self.parent.decrypt_password,
                                                account=self.parent.account,
                                                warehouse=self.parent.warehouse,
                                                database=self.parent.database,
                                                schema=self.parent.schema,
                                                ocsp_fail_open=True
                                                )
                self.parent.display_info('Authenticated via Snowflake')
            else:
                con = snowflake.connector.connect(
                                                user=self.parent.user,
                                                password=self.parent.decrypt_password,
                                                authenticator=self.parent.okta_url,
                                                account=self.parent.account,
                                                warehouse=self.parent.warehouse,
                                                database=self.parent.database,
                                                schema=self.parent.schema,
                                                ocsp_fail_open=True
                                                )                
                self.parent.display_info('Authenticated via Okta')
 
            # Set warehouse and schema
            con.cursor().execute(f"USE WAREHOUSE {self.parent.warehouse}")
            con.cursor().execute(f"USE SCHEMA {self.parent.database}.{self.parent.schema}")

            # # fix table name if case sensitive used or keyswords
            # self.parent.table = cleaner.reserved_words(self.parent.table, self.parent.case_sensitive)
        
            # # Execute Table Creation #
            # if self.parent.sql_type in ('create', 'update'):
            #     if self.parent.sql_type == 'create':
            #         table_sql: str = f"Create or Replace table {self.parent.table}  ({', '.join([self.parent.create_sql(k,v,s,c) for k, (v,s,c) in self.sql_list.items()])}"

            #     elif self.parent.sql_type == 'update':
            #         table_sql: str = f"Create or Replace TEMPORARY TABLE tmp  ({', '.join([self.parent.create_sql(k,v,s,c) for k, (v,s,c) in self.sql_list.items()])}"

            #     table_sql += f', PRIMARY KEY ({self.parent.key}))' if self.parent.key else ')'

            #     con.cursor().execute(table_sql)

            # # PUT and COPY to Snowflake

            # if self.parent.sql_type == 'truncate':
            #     con.cursor().execute(f'truncate table {self.parent.table}')

            # if self.parent.sql_type in ('create', 'truncate', 'append'):
            #     con.cursor().execute("PUT 'file://{0}*' @%{1} PARALLEL=64 OVERWRITE=TRUE".format(gzip_file, self.parent.table))
            #     con.cursor().execute("""COPY INTO {0} FILE_FORMAT = (TYPE=CSV FIELD_DELIMITER='|' NULL_IF='NULL' COMPRESSION=GZIP SKIP_HEADER=1 FIELD_OPTIONALLY_ENCLOSED_BY='"') PURGE = TRUE""".format(self.parent.table))

            # elif self.parent.sql_type == 'update':
            #     con.cursor().execute("PUT 'file://{0}*' @%tmp PARALLEL=64 OVERWRITE=TRUE".format(gzip_file))
            #     con.cursor().execute("""COPY INTO tmp FILE_FORMAT = (TYPE=CSV FIELD_DELIMITER='|' NULL_IF='NULL' COMPRESSION=GZIP SKIP_HEADER=1 FIELD_OPTIONALLY_ENCLOSED_BY='"') PURGE = TRUE""")


            #     insert_fields = ', '.join(self.sql_list)
            #     set_fields = ', '.join([f + ' = tmp.' + f for f in self.sql_list])
            #     tmp_fields = (', ').join(['tmp.' + fld for fld in self.sql_list])

            #     merge_query = (f'merge into {self.parent.table} '
            #                         f'using tmp on {self.parent.table}.{self.parent.key} = tmp.{self.parent.key} '
            #                         f'when matched then '
            #                         f'update set {set_fields} '
            #                         f'when not matched then '
            #                         f'insert ({insert_fields}) values ({tmp_fields});')

            #     con.cursor().execute(merge_query)

            for ddl in self.field_list:
                con.cursor().execute(f'{ddl}')
                self.parent.display_info(f'{ddl}')

            self.parent.display_info(f'Processed {self.counter:,} records')
            
            if self.parent.suspend_wh:
                con.cursor().execute(f'alter warehouse {self.parent.warehouse} suspend')
                self.parent.display_info('Suspended the warehouse')

        except Exception as e:
            logging.error(str(e))
            self.parent.display_error_msg(f'Error {e.errno} ({e.sqlstate}): {e.msg} ({e.sfqid})')
        finally:

            # delete temporary files if selected
            # Get a list of all the file paths that ends with .txt from in specified directory
            # if self.parent.delete_tempfiles:
            #     fileList = glob.glob(f'{self.parent.temp_dir}/*.gz')
            #     # Iterate over the list of filepaths & remove each file.
            #     for filePath in fileList:
            #         try:
            #             self.parent.display_info(f'Removed temp file {filePath}')
            #             os.remove(filePath)
            #         except:
            #             self.parent.display_info(f'Unable to remove temp file {filePath}')

            if con:
                con.close()

        self.parent.display_info('Snowflake transaction complete')