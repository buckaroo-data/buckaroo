# -*- coding: utf-8 -*-
import os
import pandas as pd
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from flask_cors import cross_origin
from ..extensions import db
import json
#from .dcf_transform import dcf_transform, s, dcf_to_py as dcf_to_py_core
from .lispy import s
from .all_transforms import dcf_transform, dcf_to_py_core, command_patterns, command_defaults
#from lispy import s
dcf_views = Blueprint('dcf', __name__, url_prefix='/dcf')


#make an @serve_df decorator that deals with query params and converting the df

DEFAULT_CSV_PATH = './sample_data/2014-01-citibike-tripdata.csv'
#DEFAULT_CSV_PATH = './sample_data/problem.csv'
csv_path = os.getenv('DCF_CSV', DEFAULT_CSV_PATH)

@dcf_views.route('/df/<id>', methods=['GET'])
@cross_origin()
def read_df(id):

    df = pd.read_csv(csv_path)
    slice_start = int(request.args.get('slice_start', 0))
    slice_end = request.args.get('slice_end', False)
    if slice_end is not False:
        df = df[slice_start:int(slice_end)]
    return json.loads(df.to_json(orient='table', indent=2))


@dcf_views.route('/transform_df/<id>', methods=['GET'])
@cross_origin()
def transform_df(id):
    df = pd.read_csv(csv_path)
    instructions = json.loads(request.args.get('instructions', None))

    #slice before or after??? probably after, otherwise run a dcf command
    df = dcf_transform(instructions, df)

    slice_start = int(request.args.get('slice_start', 0))
    slice_end = request.args.get('slice_end', False)
    
    if slice_end is not False:
        df = df.iloc[slice_start:int(slice_end)]
    return json.loads(df.to_json(orient='table', indent=2))


@dcf_views.route('/dcf_to_py/<id>', methods=['GET'])
@cross_origin()
def dcf_to_py(id):
    instructions = json.loads(request.args.get('instructions', None))
    #return dcf_to_py(instructions)
    try:
        py_string = dcf_to_py_core(instructions)
        return dict(py=py_string)
    except Exception as e:
        print("e", e)
        return "error"
    


@dcf_views.route('/command-config', methods=['GET'])
@cross_origin()
def command_config():
    sym = s

    commandPatterns = {
        "dropcol":[None],
        "fillna":[[3, 'fillVal', 'type', 'integer']],
        "groupby":[[3, 'colMap', 'colEnum', ['null', 'sum', 'mean', 'count']]]
    }
    commandDefaults = {
        "dropcol":  [sym("dropcol"), sym("df"), "col"],
        "fillna":   [sym("fillna"), sym("df"), "col", 8],
        "groupby": [sym("resample"), sym('df'), 'col', {}]
    }
    #return dict(commandPatterns=commandPatterns, commandDefaults=commandDefaults)
    return dict(commandPatterns=command_patterns, commandDefaults=command_defaults)
    

