"""
Very simple web server for Alpino
"""
import os
import subprocess
import tempfile
import logging

import sys
from KafNafParserPy import KafNafParser
from lxml.etree import XMLSyntaxError

import alpinonaf
from flask import Flask, request, jsonify, Response, make_response
from io import BytesIO

app = Flask('NewsreaderServer')


NAF_HEADER = {'Content-type': 'application/naf+xml',
              'Content-Disposition': 'attachment; filename="result.naf"'}


@app.route('/', methods=['GET'])
def index():
    return 'Simple web API for alpino, see  this <a href="/parse?text=dit is een test">example</a>) and see <a href="http://github.com/vanatteveldt/alpino-server">vanatteveldt/alpino-server</a> for more information.', 200


@app.route('/parse/<modules>', methods=['GET', 'POST'])
def parse(modules="alpino"):
    modules = modules.split(",")

    if request.method == "GET":
        data = request.args.get('text', None).encode("utf-8")
    else:
        data = request.get_data()
    if not data:
        return "Please provide text as POST data or GET text= parameter\n", 400
    result = do_parse(data, modules)
    return Response(result, mimetype='text/xml')


def do_parse(data: bytes, modules: [str]) -> bytes:
    try:
        functions = [getattr(Modules, module) for module in modules]
    except AttributeError as e:
        raise Exception("Uknown module: {e}".format(**locals()))

    for function in functions:
        print(">>", function, type(data))
        data = function(data)
        print("<<", function, type(data))

    return data


class Modules(object):
    @classmethod
    def alpino(cls, data: bytes) -> bytes:
        data = BytesIO(data)
        try:
            data = KafNafParser(data)
        except XMLSyntaxError:
            pass  # alpino can parse raw text
        return dump_naf(alpinonaf.parse(data))

    @classmethod
    def nerc(cls, data: bytes) -> bytes:
        if not ("NERC_JAR" in os.environ and "NERC_MODEL" in os.environ):
            raise Exception("Please specify NERC_JAR and NERC_MODEL!")
        nerc_jar = os.environ["NERC_JAR"]
        nerc_model = os.environ["NERC_MODEL"]
        if not os.path.exists(nerc_jar):
            raise Exception("NERC jar not found at {nerc_jar}".format(**locals()))
        if not os.path.exists(nerc_model):
            raise Exception("NERC model not found at {nerc_model}".format(**locals()))
        cmd=["java", "-jar", nerc_jar, "tag", "-m", nerc_model]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        out, _err = p.communicate(data)
        return out

    @classmethod
    def coref(cls, data: bytes) -> bytes:
        if 'COREF_ENV' in os.environ:
            executable = os.path.join(os.environ['COREF_ENV'], 'bin', 'python')
        else:
            executable = sys.executable
        command = [executable, "-m", "multisieve_coreference.resolve_coreference"]

        p = subprocess.Popen(command, shell=False, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        out, err = p.communicate(data)
        if err:
            raise Exception(err)
        if not out:
            raise Exception("No output from coreference and no error message")

        return out


def dump_naf(naf):
    out = BytesIO()
    naf.dump(out)
    return out.getvalue()


if __name__ == '__main__':
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=5002,
                        help="Port number to listen to (default: 5001)")
    parser.add_argument("--host", "-H", help="Host address to listen on (default: localhost)")
    parser.add_argument("--debug", "-d", help="Set debug mode", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

    app.run(port=args.port, host=args.host, debug=args.debug, threaded=True)
