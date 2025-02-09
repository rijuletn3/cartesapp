

dev_image_template = '''
# syntax=docker.io/docker/dockerfile:1.4
FROM ubuntu:22.04

RUN <<EOF
apt update
apt install -y --no-install-recommends \
    ca-certificates \
    wget
EOF

WORKDIR /opt/cartesi/dev
RUN chmod 777 .

ARG NONODO_VERSION=1.0.2

COPY --from=ghcr.io/foundry-rs/foundry:latest /usr/local/bin/anvil /usr/local/bin/anvil

RUN wget https://github.com/Calindra/nonodo/releases/download/v${NONODO_VERSION}/nonodo-v${NONODO_VERSION}-linux-$(dpkg --print-architecture).tar.gz -qO - | \
    tar xzf - -C /usr/local/bin nonodo

RUN apt remove -y wget ca-certificates && apt -y autoremove

EXPOSE 5004
EXPOSE 8080
EXPOSE 8545
'''

reader_image_template = '''
# syntax=docker.io/docker/dockerfile:1.4
FROM cartesi/sdk:{{ config['sdkversion'] }}

WORKDIR /opt/cartesi/reader
RUN chmod 777 .

ARG CM_CALLER_VERSION=0.1.1
ARG NONODO_VERSION=1.0.2

COPY --from=ghcr.io/foundry-rs/foundry:latest /usr/local/bin/anvil /usr/local/bin/anvil

RUN curl -s -L https://github.com/Calindra/nonodo/releases/download/v${NONODO_VERSION}/nonodo-v${NONODO_VERSION}-linux-$(dpkg --print-architecture).tar.gz | \
    tar xzf - -C /usr/local/bin nonodo

RUN curl -s -L https://github.com/lynoferraz/cm-caller/releases/download/v${CM_CALLER_VERSION}/cm-caller-v${CM_CALLER_VERSION}-linux-$(dpkg --print-architecture).tar.gz | \
    tar xzf - -C /usr/local/bin cm-caller

EXPOSE 8080
EXPOSE 8545
'''

cm_image_template = '''
# syntax=docker.io/docker/dockerfile:1.4
ARG CARTESI_SDK_VERSION={{ config.get('CARTESI_SDK_VERSION') or "0.6.2" }}
ARG MACHINE_EMULATOR_TOOLS_VERSION={{ config.get('MACHINE_EMULATOR_TOOLS_VERSION') or "0.14.1" }}

FROM --platform=linux/riscv64 cartesi/python:3.10-slim-jammy as base

ARG CARTESI_SDK_VERSION
ARG MACHINE_EMULATOR_TOOLS_VERSION

LABEL io.CARTESI.sdk_version=${CARTESI_SDK_VERSION}
LABEL io.cartesi.rollups.ram_size=128Mi


ADD https://github.com/cartesi/machine-emulator-tools/releases/download/v${MACHINE_EMULATOR_TOOLS_VERSION}/machine-emulator-tools-v${MACHINE_EMULATOR_TOOLS_VERSION}.deb /
RUN dpkg -i /machine-emulator-tools-v${MACHINE_EMULATOR_TOOLS_VERSION}.deb \
  && rm /machine-emulator-tools-v${MACHINE_EMULATOR_TOOLS_VERSION}.deb

ARG DEBIAN_FRONTEND=noninteractive
RUN <<EOF
set -e
apt-get update && \
apt-get install -y --no-install-recommends build-essential=12.9ubuntu3 \
  busybox-static=1:1.30.1-7ubuntu3 sqlite3=3.37.2-2ubuntu0.3 git=1:2.34.1-1ubuntu1.10 && \
rm -rf /var/lib/apt/lists/* /var/log/* /var/cache/* && \
useradd --create-home --user-group dapp
EOF

ENV PATH="/opt/cartesi/bin:${PATH}"

WORKDIR /opt/cartesi/dapp
COPY ./requirements.txt .

RUN <<EOF
set -e
pip install -r requirements.txt --no-cache
find /usr/local/lib -type d -name __pycache__ -exec rm -r {} +
EOF

ENV ROLLUP_HTTP_SERVER_URL="http://127.0.0.1:5004"

# Automatic copying the modules here
{% for module in modules -%}
COPY {{ module }} {{ module }}
{% endfor %}
FROM base as dapp

ENTRYPOINT ["rollup-init"]
CMD ["cartesapp","run","--log-level","info"]
'''

makefile_template = '''
# Makefile

ENVFILE := .env

SHELL := /bin/bash

define setup_venv =
@if [ ! -d .venv ]; then python3 -m venv .venv; fi
@if [[ "VIRTUAL_ENV" != "" ]]; then . .venv/bin/activate; fi
@if [ -z "$(pip freeze)" ]; then
	if [ -f requirements.txt ]; then 
		pip install -r requirements.txt;
	else
		pip install git+https://github.com/prototyp3-dev/cartesapp@main --find-links https://prototyp3-dev.github.io/pip-wheels-riscv/wheels/
		echo --find-links https://prototyp3-dev.github.io/pip-wheels-riscv/wheels/ >> requirements.txt
		pip freeze >> requirements.txt
		pip install git+https://github.com/prototyp3-dev/cartesapp@main#egg=cartesapp[dev] --find-links https://prototyp3-dev.github.io/pip-wheels-riscv/wheels/
	fi
fi
endef

.ONESHELL:

all: build build-reader-node

setup-env: ; $(value setup_venv)

# build targets
build: ; $(value setup_venv)
	cartesapp build

build-reader-node: ; $(value setup_venv)
	cartesapp build-reader-image

build-dev-node: ; $(value setup_venv)
	cartesapp build-dev-image

build-%: --load-env-% ; $(value setup_venv)
	cartesapp build

# Run targets
run: --load-env --check-roladdr-env ; $(value setup_venv)
	cartesapp node

run-dev: --load-env --check-roladdr-env ; $(value setup_venv)
	ROLLUP_HTTP_SERVER_URL=${ROLLUP_HTTP_SERVER_URL} cartesapp node --mode dev

run-reader: ; $(value setup_venv)
	cartesapp node --mode reader

# Aux env targets
--load-env: ${ENVFILE}
	$(eval include include $(PWD)/${ENVFILE})

${ENVFILE}:
	@test ! -f $@ && echo "$(ENVFILE) not found. Creating with default values" 
	echo ROLLUP_HTTP_SERVER_URL=http://localhost:8080/rollup >> $(ENVFILE)

--load-env-%: ${ENVFILE}.%
	@$(eval include include $^)

${ENVFILE}.%:
	test ! -f $@ && $(error "file $@ doesn't exist")

--check-roladdr-env:
	@test ! -z '${ROLLUP_HTTP_SERVER_URL}' || echo "Must define ROLLUP_HTTP_SERVER_URL in env" && test ! -z '${ROLLUP_HTTP_SERVER_URL}'

'''


cartesapp_utils_template = '''/* eslint-disable */
/**
 * This file was automatically generated by cartesapp.template_generator.
 * DO NOT MODIFY IT BY HAND. Instead, run the generator,
 */
import { Signer, ethers, ContractReceipt } from "ethers";
import Ajv, { ValidateFunction } from "ajv"
import addFormats from "ajv-formats"

import { 
    advanceInput, inspect, 
    AdvanceOutput, InspectOptions, AdvanceInputOptions,
    Report as CartesiReport, Notice as CartesiNotice, Voucher as CartesiVoucher, Input as CartesiInput,
    Maybe, Proof, validateNoticeFromParams, wasVoucherExecutedFromParams, executeVoucherFromParams, 
    queryNotice, queryReport, queryVoucher, queryInput, GraphqlOptions
} from "cartesi-client";

/**
 * Configs
 */

const ajv = new Ajv();
addFormats(ajv);
ajv.addFormat("biginteger", (data) => {
    const dataTovalidate = data.startsWith('-') ? data.substring(1) : data;
    return ethers.utils.isHexString(dataTovalidate) && dataTovalidate.length % 2 == 0;
});
const abiCoder = new ethers.utils.AbiCoder();
export const CONVENTIONAL_TYPES: Array<string> = ["bytes","hex","str","int","dict","list","tuple","json"];
const MAX_SPLITTABLE_OUTPUT_SIZE = {{ MAX_SPLITTABLE_OUTPUT_SIZE }};


/**
 * Models
 */

export enum IOType {
    report,
    notice,
    voucher,
    mutationPayload,
    queryPayload
}

interface ModelInterface<T> {
    ioType: IOType;
    abiTypes: Array<string>;
    params: Array<string>;
    decoder?(data: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput): T;
    exporter?(data: T): string;
    validator: ValidateFunction<T>;
}

export interface Models {
    [key: string]: ModelInterface<any>;
}

export interface InspectReportInput {
    index?: number;
    timestamp?: number
    blockNumber?: number
    msgSender?: string
}

export interface InspectReport {
    payload: string;
    input?: InspectReportInput;
    index?: number;
}

export interface OutputGetters {
    [key: string]: (o?: GraphqlOptions) => Promise<CartesiReport>|Promise<CartesiNotice>|Promise<CartesiVoucher>|Promise<CartesiInput>;
}

export const outputGetters: OutputGetters = {
    report: queryReport,
    notice: queryNotice,
    voucher: queryVoucher,
    input: queryInput
}

export interface MutationOptions extends AdvanceInputOptions {
    decode?: boolean;
}

export interface QueryOptions extends InspectOptions {
    decode?: boolean;
    decodeModel?: string;
}

export class IOData<T extends object> {
    [key: string]: any;
    _model: ModelInterface<T>

    constructor(model: ModelInterface<T>, data: T, validate: boolean = true) {
        this._model = model;
        for (const key of this._model.params) {
            this[key] = (data as any)[key];
        }
        if (validate) this.validate();
    }

    get = (): T => {
        const data: any = {};
        for (const key of this._model.params) {
            data[key] = this[key];
        }
        return data;
    }

    validate = (): boolean => {
        const dataToValidate: any = { ...this.get() };
        for (const k of Object.keys(dataToValidate)) {
            if (dataToValidate[k] === parseInt(dataToValidate[k], 10) && this._model.ioType == IOType.mutationPayload) // is int
                dataToValidate[k] = ethers.BigNumber.from(dataToValidate[k]);
            if (ethers.BigNumber.isBigNumber(dataToValidate[k]))
                dataToValidate[k] = dataToValidate[k].toHexString();
        }
        if (!this._model.validator(dataToValidate))
            throw new Error(`Data does not implement interface: ${ajv.errorsText(this._model.validator.errors)}`);     
        return true;
    }

    export(excludeParams: string[] = []): string {
        let payload: string;
        switch(this._model.ioType) {
            case IOType.mutationPayload: {
                // parametrize input to url
                const inputData: any = this.get();
                const paramList = Array<any>();
                for (const key of this._model.params) {
                    paramList.push(inputData[key]);
                }
                payload = abiCoder.encode(this._model.abiTypes,paramList);
                break;
            }
            case IOType.queryPayload: {
                // parametrize input to url
                const inputData: T = this.get();
                const paramList = Array<string>();
                for (const key in inputData) {
                    if (inputData[key] == undefined) continue;
                    if (excludeParams.indexOf(key) > -1) continue;
                    if (Array.isArray(inputData[key])) {
                        for (const element in inputData[key]) {
                            paramList.push(`${key}=${inputData[key][element]}`);
                        }
                    } else {
                        paramList.push(`${key}=${inputData[key]}`);
                    }
                }
                payload = paramList.length > 0 ? `?${paramList.join('&')}` : "";
                break;
            }
            default: {
                throw new Error(`Invalid payload type ${this._model.ioType}`);
                // break;
            }
        }
        return payload;
    }
}

export class BasicIO<T extends object> extends IOData<T> {
    _payload: string
    _inputIndex?: number
    _timestamp?: number
    _blockNumber?: number
    _msgSender?: string

    constructor(model: ModelInterface<T>, payload: string, timestamp?: number, blockNumber?: number, msgSender?: string, inputIndex?: number, proxyMsgSender: boolean = false) {
        if (proxyMsgSender) {
            msgSender = `0x${payload.slice(10,50)}`;
            payload = `0x${payload.slice(2,10)}${payload.slice(50)}`;
        }
        super(model,genericDecodeTo<T>(payload,model),false);
        this._timestamp = timestamp;
        this._blockNumber = blockNumber;
        this._msgSender = msgSender;
        this._inputIndex = inputIndex;
        this._payload = payload;
    }
}

export class BasicOutput<T extends object> extends BasicIO<T> {
    _outputIndex?: number

    constructor(model: ModelInterface<T>, payload: string, timestamp?: number, blockNumber?: number, msgSender?: string, inputIndex?: number, outputIndex?: number) {
        super(model,payload, timestamp, blockNumber, msgSender,inputIndex);
        this._outputIndex = outputIndex;
    }
}

export class Input<T extends object> extends BasicIO<T>{
    constructor(model: ModelInterface<T>, input: CartesiInput, proxyMsgSender: boolean = false) {
        super(model, input.payload, input.timestamp,input.blockNumber, input.msgSender, input.index, proxyMsgSender);
    }
}

export class Output<T extends object> extends BasicOutput<T>{
    constructor(model: ModelInterface<T>, report: CartesiReport | InspectReport) {
        super(model, report.payload, report.input?.timestamp, report.input?.blockNumber, report.input?.msgSender, report.input?.index, report.index);
    }
}

export class OutputWithProof<T extends object> extends BasicOutput<T>{
    _proof: Maybe<Proof> | undefined
    _inputIndex: number
    _outputIndex: number
    
    constructor(model: ModelInterface<T>, payload: string, timestamp: number, blockNumber: number, msgSender: string, inputIndex: number, outputIndex: number, proof: Maybe<Proof> | undefined) {
        super(model, payload, timestamp, blockNumber, msgSender, inputIndex, outputIndex);
        this._inputIndex = inputIndex;
        this._outputIndex = outputIndex;
        this._proof = proof;
    }
}

export class Event<T extends object> extends OutputWithProof<T>{
    constructor(model: ModelInterface<T>, notice: CartesiNotice) {
        super(model, notice.payload, notice.input?.timestamp, notice.input?.blockNumber, notice.input?.msgSender, notice.input.index, notice.index, notice.proof);
    }
    validateOnchain = async (signer: Signer, dappAddress: string): Promise<boolean> => {
        if (this._proof == undefined)
            throw new Error("Notice has no proof");
        return await validateNoticeFromParams(signer,dappAddress,this._payload,this._proof);
    }
}

export class ContractCall<T extends object> extends OutputWithProof<T>{
    _destination: string
    constructor(model: ModelInterface<T>, voucher: CartesiVoucher) {
        super(model, voucher.payload, voucher.input?.timestamp, voucher.input?.blockNumber, voucher.input?.msgSender, voucher.input.index, voucher.index, voucher.proof);
        this._destination = voucher.destination;
    }
    wasExecuted = async (signer: Signer, dappAddress: string): Promise<boolean> => {
        return await wasVoucherExecutedFromParams(signer,dappAddress,this._inputIndex,this._outputIndex);
    }
    execute = async (signer: Signer, dappAddress: string): Promise<ContractReceipt | null> => {
        if (this._proof == undefined)
            throw new Error("Voucher has no proof");
        return await executeVoucherFromParams(signer,dappAddress,this._destination,this._payload,this._proof);
    }
}



/*
 * Helpers
 */

// Advance
export async function genericAdvanceInput<T extends object>(
    client:Signer,
    dappAddress:string,
    selector:string,
    inputData: IOData<T>,
    options?:AdvanceInputOptions
):Promise<AdvanceOutput|ContractReceipt> {
    if (options == undefined) options = {};

    const payloadHex = inputData.export();
    const output = await advanceInput(client,dappAddress,selector + payloadHex.replace('0x',''),options).catch(
        e => {
            if (String(e.message).startsWith('0x'))
                throw new Error(ethers.utils.toUtf8String(e.message));
            throw new Error(e.message);
    });

    return output;
}

// Inspect
export async function inspectCall(
    payload:string,
    options:InspectOptions
):Promise<InspectReport> {
    options.decodeTo = "no-decode";
    const inspectResult: string = await inspect(payload,options).catch(
        e => {
            if (String(e.message).startsWith('0x'))
                throw new Error(ethers.utils.toUtf8String(e.message));
            throw new Error(e.message);
    }) as string; // hex string
    return {payload:inspectResult};
}

export async function genericInspect<T extends object>(
    inputData: IOData<T>,
    route: string,
    options?:InspectOptions
):Promise<InspectReport> {
    if (options == undefined) options = {};
    options.aggregate = true;
    const excludeParams: string[] = [];
    const matchRoute = route.matchAll(/\{(\w+)\}/g);
    for (const m of matchRoute) {
        route = route.replace(m[0],inputData[m[1]]);
        excludeParams.push(m[1]);
    }
    const payload = `${route}${inputData.export(excludeParams)}`
    return await inspectCall(payload,options);
}

// Decode
export function genericDecodeTo<T extends object>(data: string,model: ModelInterface<T>): T {
    let dataObj: any;
    switch(model.ioType) {
        /*# case mutationPayload: {
            break;
        }
        case queryPayload: {
            break;
        }*/
        case IOType.queryPayload:
        case IOType.report: {
            const dataStr = ethers.utils.toUtf8String(data);
            try {
                dataObj = JSON.parse(dataStr);
            } catch(e) {
                throw new Error(dataStr);
            }
            dataObj = JSON.parse(ethers.utils.toUtf8String(data));
            if (!model.validator(dataObj))
                throw new Error(`Data does not implement interface: ${ajv.errorsText(model.validator.errors)}`);     
            break;
        }
        case IOType.mutationPayload:
            data = "0x"+data.slice(10);
        case IOType.notice: {
            const dataValues = abiCoder.decode(model.abiTypes,data);
            dataObj = {};
            let ind = 0;
            for (const key of model.params) {
                dataObj[key] = dataValues[ind];
                ind++;
            }
            const dataToValidate = { ...dataObj };
            for (const k of Object.keys(dataToValidate)) {
                if (ethers.BigNumber.isBigNumber(dataToValidate[k]))
                    dataToValidate[k] = dataToValidate[k].toHexString();
            }
            if (!model.validator(dataToValidate))
                throw new Error(`Data does not implement interface: ${ajv.errorsText(model.validator.errors)}`);     
            
            break;
        }
        case IOType.voucher: {
            const abiTypes: Array<string> = ["bytes4"].concat(model.abiTypes);
            const dataValues = abiCoder.decode(abiTypes,data);
            dataObj = {};
            let ind = 0;
            for (const key of model.params) {
                if (ind == 0) continue; // skip selector
                dataObj[key] = dataValues[ind-1];
                ind++;
            }
            const dataToValidate = { ...dataObj };
            for (const k of Object.keys(dataToValidate)) {
                if (ethers.BigNumber.isBigNumber(dataToValidate[k]))
                    dataToValidate[k] = dataToValidate[k].toHexString();
            }
            if (!model.validator(dataToValidate))
                throw new Error(`Data does not implement interface: ${ajv.errorsText(model.validator.errors)}`);
            break;
        }
        default: {
            throw new Error(`Cannot convert ${model.ioType}`);
            // break;
        }
    }
    return dataObj;
}

export function decodeToConventionalTypes(data: string,modelName: string): any {
    if (!CONVENTIONAL_TYPES.includes(modelName))
        throw new Error(`Cannot decode to ${modelName}`);
    switch(modelName) {
        case "bytes": {
            if (typeof data == "string") {
                if (ethers.utils.isHexString(data))
                    return ethers.utils.arrayify(data);
                else
                    throw new Error(`Cannot decode to bytes`);
            }
            return data;
        }
        case "hex": {
            return data;
        }
        case "str": {
            return ethers.utils.toUtf8String(data);
        }
        case "int": {
            if (typeof data == "string") {
                if (ethers.utils.isHexString(data))
                    return parseInt(data, 16);
                else
                    throw new Error(`Cannot decode to int`);
            }
            if (ethers.utils.isBytes(data))
                return parseInt(ethers.utils.hexlify(data), 16);
            else
                throw new Error(`Cannot decode to int`);
        }
        case "dict": case "list": case "tuple": case "json": {
            return JSON.parse(ethers.utils.toUtf8String(data));
        }
    }
}

'''
cartesapp_lib_template = '''
/* eslint-disable */
/**
 * This file was automatically generated by cartesapp.template_generator.
 * DO NOT MODIFY IT BY HAND. Instead, run the generator,
 */

import { 
    advanceInput, inspect, 
    AdvanceOutput, InspectOptions, AdvanceInputOptions, GraphqlOptions,
    PartialReport as CartesiReport, PartialNotice as CartesiNotice, PartialVoucher as CartesiVoucher, Input as CartesiInput,
    advanceDAppRelay, advanceERC20Deposit, advanceERC721Deposit, advanceEtherDeposit,
    queryNotice, queryReport, queryVoucher
} from "cartesi-client";

import { 
    InspectReport, outputGetters
} from "../cartesapp/utils"

{% if add_indexer_query -%}
import * as indexerIfaces from "../indexer/ifaces";
import * as indexerLib from "../indexer/lib"
{% endif %}



{% if add_indexer_query -%}

interface OutMap {
    [key: string]: CartesiReport | CartesiNotice | CartesiVoucher;
}
type outType = "report" | "notice" | "voucher";
type AdvanceOutputMap = Record<outType,OutMap>

export interface DecodedIndexerOutput {
    data: any[],
    page: number,
    total: number
}

export async function decodeAdvance(
    advanceResult: AdvanceOutput,
    decoder: (data: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport, modelName:string) => any,
    options?:InspectOptions): Promise<any[]>
{
    let input_index:number;
    if (advanceResult.reports.length > 0) {
        input_index = advanceResult.reports[0].input.index;
    } else if (advanceResult.notices.length > 0) {
        input_index = advanceResult.notices[0].input.index;
    } else if (advanceResult.vouchers.length > 0) {
        input_index = advanceResult.vouchers[0].input.index;
    } else {
        // Can't decode outputs (no outputs)
        return [];
    }
    const outMap: AdvanceOutputMap = {report:{},notice:{},voucher:{}};
    for (const report of advanceResult.reports) { outMap.report[report.index] = report }
    for (const notice of advanceResult.notices) { outMap.notice[notice.index] = notice }
    for (const voucher of advanceResult.vouchers) { outMap.voucher[voucher.index] = voucher }

    const indexerOutput: indexerLib.{{ indexer_output_info['model'].__name__ }} = await indexerLib.{{ convert_camel_case(indexer_query_info['method']) }}({input_index:input_index},{...options, decode:true, decodeModel:"{{ indexer_output_info['model'].__name__ }}"}) as indexerLib.{{ indexer_output_info['model'].__name__ }};

    const outList: any[] = [];
    for (const indOut of indexerOutput.data) {
        outList.push( decoder(outMap[indOut.type as outType][`${indOut.output_index}`],indOut.class_name) );
    }
    return outList
}

// indexer
export async function genericGetOutputs(
    inputData: indexerIfaces.{{ indexer_query_info['model'].__name__ }},
    decoder: (data: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput, modelName:string) => any,
    options?:InspectOptions
):Promise<DecodedIndexerOutput> {
    if (options == undefined) options = {};
    const indexerOutput: indexerLib.{{ indexer_output_info['model'].__name__ }} = await indexerLib.{{ convert_camel_case(indexer_query_info['method']) }}(inputData,{...options, decode:true, decodeModel:"{{ indexer_output_info['model'].__name__ }}"}) as indexerLib.{{ indexer_output_info['model'].__name__ }};
    const graphqlQueries: Promise<any>[] = [];
    for (const outInd of indexerOutput.data) {
        const graphqlOptions: GraphqlOptions = {cartesiNodeUrl: options.cartesiNodeUrl, inputIndex: outInd.input_index, outputIndex: outInd.output_index};
        graphqlQueries.push(outputGetters[outInd.type](graphqlOptions).then(
            (output: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput) => {
                return decoder(output,outInd.class_name);
            }
        ));
    }
    return Promise.all(graphqlQueries).then((data: any[]) => {return {page:indexerOutput.page, total:indexerOutput.total, data:data};});
}
{% endif %}

'''

lib_template_std_imports = '''/* eslint-disable */
/**
 * This file was automatically generated by cartesapp.template_generator.
 * DO NOT MODIFY IT BY HAND. Instead, run the generator,
 */
import { ethers, Signer, ContractReceipt } from "ethers";

import { 
    advanceInput, inspect, 
    AdvanceOutput, InspectOptions, AdvanceInputOptions, GraphqlOptions,
    EtherDepositOptions, ERC20DepositOptions, ERC721DepositOptions,
    Report as CartesiReport, Notice as CartesiNotice, Voucher as CartesiVoucher, Input as CartesiInput,
    advanceDAppRelay, advanceERC20Deposit, advanceERC721Deposit, advanceEtherDeposit,
    queryNotice, queryReport, queryVoucher
} from "cartesi-client";

'''

lib_template = '''
import Ajv from "ajv"
import addFormats from "ajv-formats"

import { 
    genericAdvanceInput, genericInspect, IOType, Models,
    IOData, Input, Output, Event, ContractCall, InspectReport, 
    MutationOptions, QueryOptions, 
    CONVENTIONAL_TYPES, decodeToConventionalTypes
} from "../cartesapp/utils"

{% if has_indexer_query -%}
import { 
    genericGetOutputs, decodeAdvance, DecodedIndexerOutput
} from "../cartesapp/lib"

import * as indexerIfaces from "../indexer/ifaces"
{% endif -%}

import * as ifaces from "./ifaces";


/**
 * Configs
 */

const ajv = new Ajv();
addFormats(ajv);
ajv.addFormat("biginteger", (data) => {
    const dataTovalidate = data.startsWith('-') ? data.substring(1) : data;
    return ethers.utils.isHexString(dataTovalidate) && dataTovalidate.length % 2 == 0;
});
const MAX_SPLITTABLE_OUTPUT_SIZE = {{ MAX_SPLITTABLE_OUTPUT_SIZE }};

/*
 * Mutations/Advances
 */

{% for info in mutations_info -%}
export async function {{ convert_camel_case(info['method']) }}(
    client:Signer,
    dappAddress:string,
    inputData: ifaces.{{ convert_camel_case(info['model'].__name__,True) }},
    options?:MutationOptions
):Promise<AdvanceOutput|ContractReceipt|any[]> {
    const data: {{ convert_camel_case(info['model'].__name__,True) }} = new {{ convert_camel_case(info['model'].__name__,True) }}(inputData);
    {% if has_indexer_query -%}
    if (options?.decode) { options.sync = true; }
    const result = await genericAdvanceInput<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}>(client,dappAddress,'{{ "0x"+info["selector"].to_bytes().hex() }}',data, options)
    if (options?.decode) {
        return decodeAdvance(result as AdvanceOutput,decodeToModel,options);
    }
    return result;
{% else -%}
    return genericAdvanceInput<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}>(client,dappAddress,'{{ "0x"+info["selector"].to_bytes().hex() }}',data, options);
{% endif -%}
}

{% endfor %}
/*
 * Queries/Inspects
 */

{% for info in queries_info -%}
export async function {{ convert_camel_case(info['method']) }}(
    inputData: ifaces.{{ convert_camel_case(info['model'].__name__,True) }},
    options?:QueryOptions
):Promise<InspectReport|any> {
    const route = '{{ info["selector"] }}';
    {# return genericInspect<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}>(data,route,options); -#}
    {% if info["configs"].get("splittable_output") -%}
    let part:number = 0;
    let hasMoreParts:boolean = false;
    const output: InspectReport = {payload: "0x"}
    do {
        hasMoreParts = false;
        let inputDataSplittable = Object.assign({part},inputData);
        const data: {{ convert_camel_case(info['model'].__name__,True) }} = new {{ convert_camel_case(info['model'].__name__,True) }}(inputDataSplittable);
        const partOutput: InspectReport = await genericInspect<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}>(data,route,options);
        let payloadHex = partOutput.payload.substring(2);
        if (payloadHex.length/2 > MAX_SPLITTABLE_OUTPUT_SIZE) {
            part++;
            payloadHex = payloadHex.substring(0, payloadHex.length - 2);
            hasMoreParts = true;
        }
        output.payload += payloadHex;
    } while (hasMoreParts)
    {% else -%}
    const data: {{ convert_camel_case(info['model'].__name__,True) }} = new {{ convert_camel_case(info['model'].__name__,True) }}(inputData);
    const output: InspectReport = await genericInspect<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}>(data,route,options);
    {% endif -%}
    if (options?.decode) { return decodeToModel(output,options.decodeModel || "json"); }
    return output;
}

{% endfor %}
{% if has_indexer_query -%}
/*
 * Indexer Query
 */

export async function getOutputs(
    inputData: indexerIfaces.IndexerPayload,
    options?:InspectOptions
):Promise<DecodedIndexerOutput> {
    return genericGetOutputs(inputData,decodeToModel,options);
}
{% endif %}

/**
 * Models Decoders/Exporters
 */

export function decodeToModel(data: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput, modelName: string): any {
    if (modelName == undefined)
        throw new Error("undefined model");
    if (CONVENTIONAL_TYPES.includes(modelName))
        return decodeToConventionalTypes(data.payload,modelName);
    const decoder = models[modelName].decoder;
    if (decoder == undefined)
        throw new Error("undefined decoder");
    return decoder(data);
}

export function exportToModel(data: any, modelName: string): string {
    const exporter = models[modelName].exporter;
    if (exporter == undefined)
        throw new Error("undefined exporter");
    return exporter(data);
}

{% for info in mutations_payload_info -%}
{% if info['model'] -%}
export class {{ convert_camel_case(info['model'].__name__,True) }}Input extends Input<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}> { constructor(data: CartesiInput) { super(models['{{ info["model"].__name__ }}'],data{% if info.get('has_proxy') -%},true{% endif -%}); } }
export function decodeTo{{ convert_camel_case(info['model'].__name__,True) }}Input(output: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput): {{ convert_camel_case(info['model'].__name__,True) }}Input {
    return new {{ convert_camel_case(info['model'].__name__,True) }}Input(output as CartesiInput);
}

export class {{ convert_camel_case(info['model'].__name__,True) }} extends IOData<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}> { constructor(data: ifaces.{{ info["model"].__name__ }}, validate: boolean = true) { super(models['{{ info["model"].__name__ }}'],data,validate); } }
export function exportTo{{ convert_camel_case(info['model'].__name__,True) }}(data: ifaces.{{ info["model"].__name__ }}): string {
    const dataToExport: {{ convert_camel_case(info['model'].__name__,True) }} = new {{ convert_camel_case(info['model'].__name__,True) }}(data);
    return dataToExport.export();
}
{% endif -%}

{% endfor -%}
{% for info in queries_payload_info -%}
{% if info['model'] -%}
export class {{ convert_camel_case(info['model'].__name__,True) }}Input extends Input<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}> { constructor(data: CartesiInput) { super(models['{{ info["model"].__name__ }}'],data); } }
export function decodeTo{{ convert_camel_case(info['model'].__name__,True) }}Input(output: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput): {{ convert_camel_case(info['model'].__name__,True) }}Input {
    return new {{ convert_camel_case(info['model'].__name__,True) }}Input(output as CartesiInput);
}

export class {{ convert_camel_case(info['model'].__name__,True) }} extends IOData<ifaces.{{ convert_camel_case(info['model'].__name__,True) }}> { constructor(data: ifaces.{{ info["model"].__name__ }}, validate: boolean = true) { super(models['{{ info["model"].__name__ }}'],data,validate); } }
export function exportTo{{ convert_camel_case(info['model'].__name__,True) }}(data: ifaces.{{ info["model"].__name__ }}): string {
    const dataToExport: {{ convert_camel_case(info['model'].__name__,True) }} = new {{ convert_camel_case(info['model'].__name__,True) }}(data);
    return dataToExport.export();
}
{% endif -%}

{% endfor -%}
{% for info in reports_info -%}
export class {{ convert_camel_case(info['class'],True) }} extends Output<ifaces.{{ convert_camel_case(info['class'],True) }}> { constructor(output: CartesiReport | InspectReport) { super(models['{{ info["class"] }}'],output); } }
export function decodeTo{{ convert_camel_case(info['class'],True) }}(output: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput): {{ convert_camel_case(info['class'],True) }} {
    return new {{ convert_camel_case(info['class'],True) }}(output as CartesiReport);
}

{% endfor -%}
{% for info in notices_info -%}
export class {{ convert_camel_case(info['class'],True) }} extends Event<ifaces.{{ convert_camel_case(info['class'],True) }}> { constructor(output: CartesiNotice) { super(models['{{ info["class"] }}'],output); } }
export function decodeTo{{ convert_camel_case(info['class'],True) }}(output: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput): {{ convert_camel_case(info['class'],True) }} {
    return new {{ convert_camel_case(info['class'],True) }}(output as CartesiNotice);
}

{% endfor -%}
{% for info in vouchers_info -%}
export class {{ convert_camel_case(info['class'],True) }} extends ContractCall<ifaces.{{ convert_camel_case(info['class'],True) }}> { constructor(output: CartesiVoucher) { super(models['{{ info["class"] }}'],output); } }
export function decodeTo{{ convert_camel_case(info['class'],True) }}(output: CartesiReport | CartesiNotice | CartesiVoucher | InspectReport | CartesiInput): {{ convert_camel_case(info['class'],True) }} {
    return new {{ convert_camel_case(info['class'],True) }}(output as CartesiVoucher);
}

{% endfor %}
/**
 * Model
 */

export const models: Models = {
    {% for info in mutations_payload_info -%}
    '{{ info["model"].__name__ }}': {
        ioType:IOType.mutationPayload,
        abiTypes:{{ info['abi_types'] }},
        params:{{ list(info["model"].__fields__.keys()) }},
        decoder: decodeTo{{ convert_camel_case(info["model"].__name__,True) }}Input,
        exporter: exportTo{{ info["model"].__name__ }},
        validator: ajv.compile<ifaces.{{ info["model"].__name__ }}>(JSON.parse('{{ info["model"].schema_json() }}'.replaceAll('integer','string","format":"biginteger')))
    },
    {% endfor -%}
    {% for info in queries_payload_info -%}
    '{{ info["model"].__name__ }}': {
        ioType:IOType.queryPayload,
        abiTypes:{{ info['abi_types'] }},
        params:{{ list(info["model"].__fields__.keys()) }},
        decoder: decodeTo{{ convert_camel_case(info["model"].__name__,True) }}Input,
        exporter: exportTo{{ info["model"].__name__ }},
        validator: ajv.compile<ifaces.{{ info["model"].__name__ }}>(JSON.parse('{{ info["model"].schema_json() }}'))
    },
    {% endfor -%}
    {% for info in reports_info -%}
    '{{ info["class"] }}': {
        ioType:IOType.report,
        abiTypes:{{ info['abi_types'] }},
        params:{{ list(info["model"].__fields__.keys()) }},
        decoder: decodeTo{{ convert_camel_case(info['class'],True) }},
        validator: ajv.compile<ifaces.{{ convert_camel_case(info['class'],True) }}>(JSON.parse('{{ info["model"].schema_json() }}'))
    },
    {% endfor -%}
    {% for info in notices_info -%}
    '{{ info["class"] }}': {
        ioType:IOType.notice,
        abiTypes:{{ info['abi_types'] }},
        params:{{ list(info["model"].__fields__.keys()) }},
        decoder: decodeTo{{ convert_camel_case(info['class'],True) }},
        validator: ajv.compile<ifaces.{{ convert_camel_case(info['class'],True) }}>(JSON.parse('{{ info["model"].schema_json() }}'.replaceAll('integer','string","format":"biginteger')))
    },
    {% endfor -%}
    {% for info in vouchers_info -%}
    '{{ info["class"] }}': {
        ioType:IOType.voucher,
        abiTypes:{{ info['abi_types'] }},
        params:{{ list(info["model"].__fields__.keys()) }},
        decoder: decodeTo{{ convert_camel_case(info['class'],True) }},
        validator: ajv.compile<ifaces.{{ convert_camel_case(info['class'],True) }}>(JSON.parse('{{ info["model"].schema_json() }}'.replaceAll('integer','string","format":"biginteger')))
    },
    {% endfor -%}
};
'''
