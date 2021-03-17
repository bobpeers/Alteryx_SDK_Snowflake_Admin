# Alteryx SDK Snowflake Admin
Custom Alteryx tool to run administrative DDL commands against a Snowflake Database.

## Description
This is an Alteryx tool to run arbitrary SQL commands against a Snowflake Database. This allows you to run administrative DDL commands such as:

- ALTER <object>
- COMMENT
- CREATE <object>
- DESCRIBE <object>
- DROP <object>
- SHOW <objects>
- USE <object>

Full documentation on the DDL command can be found on [Snowflakes page](https://docs.snowflake.com/en/sql-reference/sql-ddl-summary.html).

## Installation
Download the yxi file and double click to install in Alteryx.

<img src="https://user-images.githubusercontent.com/4363445/111472549-5c30a480-872a-11eb-906c-8512ea09d21e.png" width='500px' alt="Snowflake Admin Install Dialog">

The tool will be installed in the __Connectors__ category.

## Configuration
Fill in the standard Snowflake configuration.

If you wish the warehouse to be suspended immediately after running select the checkbox under Advanced Options.

<img src="https://user-images.githubusercontent.com/4363445/111470688-69e52a80-8728-11eb-96a9-212544686203.png" width="500" alt="Snowflake Admin Config">

## Authorisation
This can be either via Snowflake or Okta. If you select Okta authentication this must be set up on the server according to the [Snowflake Instructions](https://docs.snowflake.com/en/user-guide/admin-security-fed-auth-configure-snowflake.html). 

<img src='https://github.com/bobpeers/Alteryx_SDK_Snowflake_Output/blob/main/images/okta.gif' width=500px alt='Snowflake Okta Authentication'>

## Usage
The tool will run the raw text contained in the field you mao to the  **SQL command field**. There are no safety controls on threse statements so assuming you have permissions on the Snowflake Database any command will be run. **USE WITH CAUTION**.

## Logging
The tool will create log files for each run in the temp folder supplied. These logs contain detailed information on the Snowflake connection and can be used in case of unexected errors.

## Outputs
The tool has no output.

## Requirements

The tool installs the official [Snowflake Connector library](https://docs.snowflake.com/en/user-guide/python-connector.html)
