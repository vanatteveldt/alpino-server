"""
Very simple web server for Alpino
"""
import os
import subprocess
import tempfile
import logging

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


@app.route('/parse/', methods=['GET', 'POST'])
@app.route('/parse/<output>', methods=['GET', 'POST'])
def parse(output="dependencies"):
    tokenized = request.args.get('tokenized', "N") in ('Y', 'y', '1', 1)
    if request.method == "GET":
        body = request.args.get('text', None).encode("utf-8")
    else:
        body = request.get_data()

    if not body:
        raise Exception("Please provide text as POST data or GET text= parameter")

    if output == 'naf':
        return Response(parse_naf(BytesIO(body)), status=200, headers=NAF_HEADER)
    elif output == 'nerc':
        parsed = get_parsed_naf(body)
        result = do_nerc(parsed)
        return Response(result, status=200, headers=NAF_HEADER)
    else:
        result = parse(body.decode("utf-8"), output, tokenized)
        return jsonify(result), 200


def parse_naf(input):
    out = BytesIO()
    alpinonaf.parse(input).dump(out)
    return out.getvalue()


def do_nerc(input):
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
    out, _err = p.communicate(input)
    return out




def get_parsed_naf(body):
    try:
        naf = KafNafParser(BytesIO(body))
        deps = list(naf.get_dependencies())
        if deps:
            logging.debug("Input already parsed")
            return body
        else:
            logging.debug("Parsing from NAF")
            return parse_naf(naf)
    except XMLSyntaxError:
        logging.debug("Parsing from raw text")
        return parse_naf(BytesIO(body))


# Alpino functions
CMD_TOKENIZE = ["Tokenization/tok"]


def tokenize(text: str) -> str:
    return call_alpino_stdout(CMD_TOKENIZE, text).replace("|", "")


def parse(text, output='dependencies', tokenized=False):
    """Parse the text to the given output

    Output matches to end_hook except for treebank_triples,
    which calls with end_hook=xml first followed by a call to treebank_triples,

    :param text: untokenized text to parse (str)
    :param output: output format, one of {"dependencies", "xml", "treebank_triples"}
    :return: depending on output: for dependencies, a list of depency tuples;
             for xml, a dict of {fn: "xml"};
             for treebank_triples, a dict {"fn": {"triples": [triples], xml: "xml"}}
    """

    if not tokenized:
        text = tokenize(text)
    if output == "dependencies":
        return alpino_dependencies(text)
    elif output  == "xml":
        return alpino_xml(text)
    elif output == "treebank_triples":
        return alpino_treebank_triples(text)
    else:
        raise ValueError("Unknown output: {}".format(output))


def alpino_dependencies(tokens: str) -> dict:
    """
    Get alpino dependencies table as list-of-lists
    :param tokens: tokenized input
    :return: a dict of {id: "triples": [triples]}}
    """
    cmd = ["bin/Alpino", "end_hook=dependencies", "-parse"]
    triples= call_alpino_stdout(cmd, tokens)
    return read_triples_into_dict(triples, {})


def read_triples_into_dict(triples: str, result: dict, strip_id: bool=False) -> dict:
    """Read the triples into the result, creating {id: {'triples': [triples]}}"""
    for row in (d for d in triples.split("\n") if d.strip()):
        fields = row.split("|")
        id = fields[-1]
        if strip_id:
            id = os.path.splitext(os.path.basename(id))[0]
        result.setdefault(id, {}).setdefault("triples", []).append(fields[:-1])
    return result


def alpino_xml(input: str) -> dict:
    """Parse the sentence into alpino xml

    :param input: the tokenized input string
    :return:  a dict of {id: "xml": xml_string}}
    """
    with tempfile.TemporaryDirectory(prefix="alpinoserver-") as d:
        return alpino_xml_raw(input, d)


def alpino_treebank_triples(input: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="alpinoserver-") as d:
        result = alpino_xml_raw(input, d)
        fns = {os.path.join(d, "{id}.xml".format(id=id)): id for id in result.keys()}
        cmd = ["bin/Alpino", "-treebank_triples"] + list(fns.keys())
        triples = call_alpino_stdout(cmd)
        for line in triples.split("\n"):
            if line.strip():
                triple, fn = line.rsplit("|", 1)
                id = os.path.basename(fn).split(".")[0]
                result[id].setdefault('triples', []).append(triple)
        return result


def alpino_xml_raw(input: str, treebank: str) -> dict:
    cmd = ["bin/Alpino", "end_hook=xml", "-parse", "-flag", "treebank", treebank]
    out, err = call_alpino(cmd, input)
    result = {os.path.splitext(fn)[0]: {"xml": open(os.path.join(treebank, fn)).read()} for fn in os.listdir(treebank)}
    if not result:
        _alpino_error(cmd, input, err)
    return result


# 'Raw' Alpino calls
def call_alpino(command, input):
    alpino_home = os.environ['ALPINO_HOME']
    p = subprocess.Popen(command, shell=False, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         cwd=alpino_home)
    return [x.decode("utf-8") for x in p.communicate(input and input.encode("utf-8"))]


def _alpino_error(command, input, err):
    if input:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="wb") as f:
            f.write(input.encode("utf-8"))
            logging.exception("Error calling Alpino, input file written to {f.name}, command was {command}"
                              .format(**locals()))
    raise Exception("Problem calling {command}, output was empty. Error: {err!r}".format(**locals()))


def call_alpino_stdout(command, input=None):
    out, err = call_alpino(command, input)
    if not out:
        _alpino_error(command, input, err)
    return out

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
