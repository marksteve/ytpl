#!/bin/sh

(cd $HOME ; [ ! -d env ] && virtualenv env)

. $HOME/env/bin/activate

python setup.py install

cp -Rf * $HOME/

