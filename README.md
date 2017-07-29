# Alpino NAF Server

Simple web interface for alpino including modules for NERC (https://github.com/ixa-ehu/ixa-pipe-nerc) and coreference (https://github.com/antske/coref_draft).

# Installing and running

The easiest way to install and run it is probably through Docker:

```{sh}
docker run -dp 5002:5002 vanatteveldt/alpino-server
```

This will start alpino server running on http port 5002. 
To test the installation, you can browse to http://localhost:5002/parse/alpino,nerc,coref?text=Piet%20herkende%20zichzelf to see the (NAF XML) parse tree of the example sentence including NER and corefer


Note that this server is not secure in any way, so please make sure that this port is not accessible from outside. 
See the [Dockerfile](Dockerfile) for more details on installing the necessary prerequisites if you choose to install from source. 

# API Usage

The API has a single endpoint, /parse/<modules>, where <modules> is a comma separated list of modules to call on the input. Currently supported modules are alpino, nerc, and coref. 

Input can be supplied as POST body and should be NAF XML. For pipelines starting with Alpino it can also be plain text. 

## Examples

To parse a single sentence and store the result into /tmp/parsed.naf
```{sh}
$ curl -sXPOST localhost:5002/parse/alpino -d "Piet herkende zichzelf" > /tmp/parsed.naf
```

To run NERC and Coreference resolution on an existing NAF document, outputting to standard out:

```{sh}
$ curl -sXPOST localhost:5002/parse/nerc,coref -d @/tmp/parsed.naf
```

To run alpino, NERC, and coreference on a text file:

```{sh}
$ echo "Jan ging naar Amsterdam. Daar kwam hij haar tegen" > /tmp/test.txt
$ curl -sXPOST localhost:5002/parse/alpino,nerc,coref -d @/tmp/test.txt
```
