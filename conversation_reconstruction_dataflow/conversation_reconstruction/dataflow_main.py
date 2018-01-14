
# -*- coding: utf-8 -*-
"""
A dataflow pipeline to reconstruct conversations on Wikipedia talk pages from ingested json files.

Run with:

python dataflow_main.py --setup_file ./setup.py
"""
from __future__ import absolute_import
import argparse
import logging
import subprocess
import json
from os import path
import urllib2
import traceback

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.options.pipeline_options import SetupOptions
from apache_beam.io.gcp import bigquery as bigquery_io 

def run(known_args, pipeline_args):
  """Main entry point; defines and runs the reconstruction pipeline."""

  pipeline_args.extend([
    '--runner=DataflowRunner',
    '--project=wikidetox-viz',
    '--staging_location=gs://wikidetox-viz-dataflow/staging',
    '--temp_location=gs://wikidetox-viz-dataflow/tmp',
    '--job_name=reconstruction-test',
    '--num_workers=30',
  ])


  pipeline_options = PipelineOptions(pipeline_args)
  with beam.Pipeline(options=pipeline_options) as p:

    # Read the text file[pattern] into a PCollection.
    filenames = (p | beam.io.Read(beam.io.BigQuerySource(query='SELECT UNIQUE(page_id) as page_id FROM [%s]'%known_args.input_table, validate=True)) 
                   | beam.ParDo(ReconstructConversation())
                   | beam.io.Write(bigquery_io.BigQuerySink(known_args.output_table, schema=known_args.output_schema, validate=True)))

class ReconstructConversation(beam.DoFn):
  def process(self, row):

#    from construct_utils import constructing_pipeline
    import logging
    from google.cloud import bigquery as bigquery_op 
    import subprocess
    input_table = "wikidetox_conversations.test_page_3_issue21" 

    logging.info('USERLOG: Work start')
    page_id = row['page_id']
    client = bigquery_op.Client(project='wikidetox-viz')
    query = ("SELECT rev_id FROM %s WHERE page_id = \"%s\" ORDER BY timestamp"%(input_table, page_id))
    query_job = client.run_sync_query(query)
    query_job.run()
    rev_ids = []

    for row in query_job.rows:
        rev_ids.append(row[0])

    construction_cmd = ['python2', '-m', 'construct_utils.run_constructor', '--table', input_table, '--revisions', json.dumps(rev_ids)]
    construct_proc = subprocess.Popen(construction_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize = 4096)
    last_revision = 'None'
    for i, line in enumerate(construct_proc.stdout): 
        output = json.loads(line)
        last_revsion = output['rev_id']
        yield output
    for i, line in enumerate(construct_proc.stderr):
        logging.info('USERLOG: Error while running the recostruction process on page %s, error information: %s' % (page_id, line))
    logging.info('USERLOG: Reconstruction on page %s complete! last revision: %s' %(page_id, last_revision))

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  parser = argparse.ArgumentParser()
  # Input BigQuery Table
  input_schema = 'sha1:STRING,user_id:STRING,format:STRING,user_text:STRING,timestamp:STRING,text:STRING,page_title:STRING,model:STRING,page_namespace:STRING,page_id:STRING,rev_id:STRING,comment:STRING, user_ip:STRING, truncated:BOOLEAN,records_count:INTEGER,record_index:INTEGER'
  parser.add_argument('--input_table',
                      dest='input_table',
                      default='wikidetox-viz:wikidetox_conversations.test_page_3_issue21',
                      help='Input table for reconstruction.')
  parser.add_argument('--input_schema',
                      dest='input_schema',
                      default=input_schema,
                      help='Input table schema.')
  # Ouput BigQuery Table
  output_schema = 'sha1:STRING,user_id:STRING,format:STRING,user_text:STRING,timestamp:STRING,text:STRING,page_title:STRING,model:STRING,page_namespace:STRING,page_id:STRING,rev_id:STRING,comment:STRING, user_ip:STRING, truncated:BOOLEAN,records_count:INTEGER,record_index:INTEGER'
  parser.add_argument('--output_table',
                      dest='output_table',
                      default='wikidetox-viz:wikidetox_conversations.reconstructed_conversation_test_page_3',
                      help='Output table for reconstruction.')
  output_schema = 'user_id:STRING,user_text:STRING, timestamp:STRING, content:STRING, parent_id:STRING, replyTo_id:STRING, indentation:INTEGER,page_id:STRING,page_title:STRING,type:STRING, id:STRING,rev_id:STRING'  
  parser.add_argument('--output_schema',
                      dest='output_schema',
                      default=output_schema,
                      help='Output table schema.')
  global known_args
  known_args, pipeline_args = parser.parse_known_args()

  run(known_args, pipeline_args)



