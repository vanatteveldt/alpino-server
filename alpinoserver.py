"""
Very simple web server for Alpino
"""
import os
import subprocess
import tempfile
import logging

from flask import Flask, request, jsonify
app = Flask('AlpinoServer')

@app.route('/', methods=['GET'])
def index():
    return 'Simple web API for alpino at /parse, (<a href="/parse?text=dit is een test">example</a>). See <a href="github.com/vanatteveldt/alpinoserver">vanatteveldt/alpinoserver</a> for more information.', 200

@app.route('/parse', methods=['GET'])
def parse_get():
    text = request.args.get('text', None)
    output = request.args.get('output', "dependencies")
    if not text:
        return "Usage: /parse?text=text_to_parse[&output=output]", 400
    result = parse(text, output=output)
    return jsonify(result)


@app.route('/parse', methods=['POST'])
def parse_post():
    body = request.get_json(force=True)
    text = body['text']
    output = body.get("output", "dependencies")
    result = parse(text, output=output)
    return jsonify(result)


# Alpino functions
CMD_TOKENIZE = ["Tokenization/tok"]


def tokenize(text: str) -> str:
    return call_alpino_stdout(CMD_TOKENIZE, text).replace("|", "")


def parse(text, output='dependencies'):
    """Parse the text to the given output

    Output matches to end_hook except for treebank_triples,
    which calls with end_hook=xml first followed by a call to treebank_triples,

    :param text: untokenized text to parse (str)
    :param output: output format, one of {"dependencies", "xml", "treebank_triples"}
    :return: depending on output: for dependencies, a list of depency tuples;
             for xml, a dict of {fn: "xml"};
             for treebank_triples, a dict {"fn": {"triples": [triples], xml: "xml"}}
    """
    tokens = tokenize(text)
    if output == "dependencies":
        return alpino_dependencies(tokens)
    elif output  == "xml":
        return alpino_xml(tokens)
    elif output == "treebank_triples":
        return alpino_treebank_triples(tokens)
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
        read_triples_into_dict(triples, result, strip_id=True)
        return result


def alpino_xml_raw(input: str, treebank: str) -> dict:
    cmd = ["bin/Alpino", "end_hook=xml", "-parse", "-flag", "treebank", treebank]
    out, err = call_alpino(cmd, input)
    print(treebank, os.listdir(treebank))
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

    logging.basicConfig(level=logging.DEBUG if (args.debug or args.verbose) else logging.INFO,
                        format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

    app.run(port=args.port, host=args.host, debug=args.debug)
