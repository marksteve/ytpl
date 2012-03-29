#!/bin/sh

(cd $HOME ; [ ! -d env ] && virtualenv env)

. $HOME/env/bin/activate

python setup.py develop

cp -Rf * $HOME/

