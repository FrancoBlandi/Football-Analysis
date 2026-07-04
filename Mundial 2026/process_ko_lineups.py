#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_ko_lineups.py — Procesa lineups KO desde WebFetch (sin CDP).
Los lineups ya contienen xG, xA, minutesPlayed inline.
"""
import json, subprocess, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR   = Path(__file__).parent
WC_RESULTS = BASE_DIR / "wc2026_wc_results.json"
FORM_PATH  = BASE_DIR / "wc2026_form.json"

DECAY     = 0.82
WC_WEIGHT = 16
N_FORM    = 20

MATCH_META = {
    12813000: {"home": "South Africa", "home_id": 4736, "away": "Canada",               "away_id": 4752, "sh": 0, "sa": 1, "pens": "away"},
    12813012: {"home": "Brazil",       "home_id": 4748, "away": "Japan",                "away_id": 4770, "sh": 2, "sa": 1, "pens": None},
    12813014: {"home": "Germany",      "home_id": 4711, "away": "Paraguay",             "away_id": 4789, "sh": 1, "sa": 1, "pens": "away"},
    12812998: {"home": "Netherlands",  "home_id": 4705, "away": "Morocco",              "away_id": 4778, "sh": 1, "sa": 1, "pens": "away"},
    12812995: {"home": "France",       "home_id": 4481, "away": "Sweden",               "away_id": 4688, "sh": 3, "sa": 0, "pens": None},
    12813001: {"home": "Mexico",       "home_id": 4781, "away": "Ecuador",              "away_id": 4757, "sh": 2, "sa": 0, "pens": None},
    12812989: {"home": "Côte d'Ivoire","home_id": 4768, "away": "Norway",               "away_id": 4475, "sh": 1, "sa": 2, "pens": None},
    12813013: {"home": "Belgium",      "home_id": 4717, "away": "Senegal",              "away_id": 4739, "sh": 3, "sa": 2, "pens": None},
    12812992: {"home": "USA",          "home_id": 4724, "away": "Bosnia & Herzegovina", "away_id": 4479, "sh": 2, "sa": 0, "pens": None},
    12813020: {"home": "England",      "home_id": 4713, "away": "DR Congo",             "away_id": 4823, "sh": 2, "sa": 1, "pens": None},
    12813004: {"home": "Spain",        "home_id": 4698, "away": "Austria",              "away_id": 4718, "sh": 3, "sa": 0, "pens": None},
}

# Lineups — flat arrays (home players first, then away, split at 2nd GK)
# Brazil-Japan is already split into home/away dicts
LINEUPS = {
    12813000: [
        {"id":539792,"name":"Ronwen Williams","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.148551,"goals":0,"goalAssist":0,"saves":5,"totalShots":0,"keyPass":0,"rating":8.2},
        {"id":936047,"name":"Khuliso Mudau","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0246906,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.0},
        {"id":1507710,"name":"Ime Okon","position":"D","minutesPlayed":90,"expectedGoals":0.0139,"expectedAssists":0.00224381,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.9},
        {"id":2058228,"name":"Mbekezeli Mbokazi","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0153668,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.2},
        {"id":837099,"name":"Aubrey Modiba","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0277495,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.7},
        {"id":881117,"name":"Teboho Mokoena","position":"M","minutesPlayed":90,"expectedGoals":0.0469,"expectedAssists":0.00602604,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.6},
        {"id":822684,"name":"Sphephelo Sithole","position":"M","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0131248,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":7.3},
        {"id":1179164,"name":"Thapelo Maseko","position":"M","minutesPlayed":86,"expectedGoals":0,"expectedAssists":0.0119286,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":6.6},
        {"id":1564998,"name":"Relebohile Mofokeng","position":"M","minutesPlayed":45,"expectedGoals":0,"expectedAssists":0.116595,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.8},
        {"id":984505,"name":"Oswin Appollis","position":"M","minutesPlayed":90,"expectedGoals":0.069,"expectedAssists":0.0310679,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":1,"rating":6.2},
        {"id":1022170,"name":"Evidence Makgopa","position":"F","minutesPlayed":86,"expectedGoals":0,"expectedAssists":0.00825802,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":1014410,"name":"Thalente Mbatha","position":"M","minutesPlayed":45,"expectedGoals":0.0086,"expectedAssists":0.0223331,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.4},
        {"id":1101745,"name":"Tshepang Moremi","position":"F","minutesPlayed":11,"expectedGoals":0,"expectedAssists":0.00230771,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":991024,"name":"Iqraam Rayners","position":"F","minutesPlayed":11,"expectedGoals":0,"expectedAssists":0.00107647,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.2},
        {"id":155736,"name":"Maxime Crépeau","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00049459,"goals":0,"goalAssist":0,"saves":1,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":984419,"name":"Alistair Johnston","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0489707,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.2},
        {"id":1469180,"name":"Moise Bombito","position":"D","minutesPlayed":59,"expectedGoals":0.2625,"expectedAssists":0.00150176,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.8},
        {"id":801411,"name":"Derek Cornelius","position":"D","minutesPlayed":90,"expectedGoals":0.3287,"expectedAssists":0.0080048,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.2},
        {"id":829207,"name":"Richie Laryea","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00595569,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":973290,"name":"Tajon Buchanan","position":"M","minutesPlayed":75,"expectedGoals":0.1757,"expectedAssists":0.00560137,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.0},
        {"id":1093229,"name":"Nathan-Dylan Saliba","position":"M","minutesPlayed":59,"expectedGoals":0,"expectedAssists":0.0172877,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.0},
        {"id":886223,"name":"Stephen Eustaquio","position":"M","minutesPlayed":90,"expectedGoals":0.1148,"expectedAssists":0.608903,"goals":1,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":5,"rating":8.8},
        {"id":902083,"name":"Liam Millar","position":"M","minutesPlayed":70,"expectedGoals":0,"expectedAssists":0.123747,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.4},
        {"id":935564,"name":"Jonathan David","position":"F","minutesPlayed":90,"expectedGoals":0.1773,"expectedAssists":0.0212082,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":1,"rating":6.0},
        {"id":1172477,"name":"Tani Oluwaseyi","position":"F","minutesPlayed":70,"expectedGoals":0.2398,"expectedAssists":0.0690842,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":0,"rating":7.1},
        {"id":1413129,"name":"Luc De Fougerolles","position":"D","minutesPlayed":31,"expectedGoals":0.0358,"expectedAssists":0.00657828,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.4},
        {"id":1411145,"name":"Niko Sigur","position":"M","minutesPlayed":31,"expectedGoals":0,"expectedAssists":0.190977,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.5},
        {"id":976313,"name":"Jacob Shaffelburg","position":"M","minutesPlayed":20,"expectedGoals":0,"expectedAssists":0.00334838,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.3},
        {"id":1119328,"name":"Promise David","position":"F","minutesPlayed":20,"expectedGoals":0.0415,"expectedAssists":0.00153794,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.5},
        {"id":843665,"name":"Alphonso Davies","position":"D","minutesPlayed":15,"expectedGoals":0,"expectedAssists":0.0558383,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.5},
    ],
    12813014: [
        {"id":8959,"name":"Manuel Neuer","position":"G","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.00092775,"goals":0,"goalAssist":0,"saves":2,"totalShots":0,"keyPass":0,"rating":7.6},
        {"id":259117,"name":"Joshua Kimmich","position":"D","minutesPlayed":120,"expectedGoals":0.1171,"expectedAssists":0.113682,"goals":0,"goalAssist":0,"saves":0,"totalShots":5,"keyPass":0,"rating":8.0},
        {"id":227672,"name":"Jonathan Tah","position":"D","minutesPlayed":120,"expectedGoals":0.0119,"expectedAssists":0.0758892,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.6},
        {"id":142622,"name":"Antonio Rüdiger","position":"D","minutesPlayed":110,"expectedGoals":0,"expectedAssists":0.0776334,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.2},
        {"id":1159759,"name":"Nathaniel Brown","position":"D","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.229949,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":6.7},
        {"id":293519,"name":"Leroy Sané","position":"M","minutesPlayed":88,"expectedGoals":0.0907,"expectedAssists":0.0775192,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.2},
        {"id":907463,"name":"Felix Nmecha","position":"M","minutesPlayed":45,"expectedGoals":0,"expectedAssists":0.00561193,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.4},
        {"id":1142251,"name":"Aleksandar Pavlović","position":"M","minutesPlayed":79,"expectedGoals":0.0449,"expectedAssists":0.0638324,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.5},
        {"id":1019322,"name":"Florian Wirtz","position":"M","minutesPlayed":110,"expectedGoals":0.0711,"expectedAssists":0.674857,"goals":0,"goalAssist":1,"saves":0,"totalShots":2,"keyPass":4,"rating":8.3},
        {"id":836705,"name":"Kai Havertz","position":"F","minutesPlayed":120,"expectedGoals":0.4521,"expectedAssists":0.0928507,"goals":1,"goalAssist":0,"saves":0,"totalShots":4,"keyPass":1,"rating":7.6},
        {"id":794298,"name":"Deniz Undav","position":"F","minutesPlayed":63,"expectedGoals":0.0339,"expectedAssists":0.00457658,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.2},
        {"id":184661,"name":"Leon Goretzka","position":"M","minutesPlayed":75,"expectedGoals":0.2503,"expectedAssists":0.0141458,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":1,"rating":6.5},
        {"id":1010231,"name":"Jamal Musiala","position":"M","minutesPlayed":57,"expectedGoals":0,"expectedAssists":0.051801,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.3},
        {"id":799046,"name":"Waldemar Anton","position":"D","minutesPlayed":41,"expectedGoals":0.1899,"expectedAssists":0.0241831,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.0},
        {"id":980623,"name":"Nick Woltemade","position":"F","minutesPlayed":32,"expectedGoals":0.2752,"expectedAssists":0.00656146,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.2},
        {"id":1014286,"name":"Malick Thiaw","position":"D","minutesPlayed":10,"expectedGoals":0,"expectedAssists":0.00233059,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":327755,"name":"Nadiem Amiri","position":"M","minutesPlayed":10,"expectedGoals":0.0321,"expectedAssists":0.00766446,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.1},
        {"id":991709,"name":"Orlando Gill","position":"G","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.0050363,"goals":0,"goalAssist":0,"saves":6,"totalShots":0,"keyPass":0,"rating":9.9},
        {"id":989801,"name":"Juan Cáceres","position":"D","minutesPlayed":99,"expectedGoals":0,"expectedAssists":0.0103127,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":220833,"name":"Gustavo Gómez","position":"D","minutesPlayed":120,"expectedGoals":0.0334,"expectedAssists":0.00169038,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.9},
        {"id":877452,"name":"José Canale","position":"D","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.0002266,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":8.0},
        {"id":333275,"name":"Junior Alonso","position":"D","minutesPlayed":119,"expectedGoals":0.1053,"expectedAssists":0.00268743,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.2},
        {"id":333373,"name":"Miguel Almirón","position":"M","minutesPlayed":90,"expectedGoals":0.0228,"expectedAssists":0.0186383,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.1},
        {"id":1015261,"name":"Damián Bobadilla","position":"M","minutesPlayed":99,"expectedGoals":0,"expectedAssists":0.0253681,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":546416,"name":"Andrés Cubas","position":"M","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.00746519,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":1105836,"name":"Matías Galarza","position":"M","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.108669,"goals":0,"goalAssist":1,"saves":0,"totalShots":0,"keyPass":1,"rating":7.1},
        {"id":789453,"name":"Gabriel Ávalos","position":"F","minutesPlayed":55,"expectedGoals":0,"expectedAssists":0.00125696,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":973556,"name":"Julio Enciso","position":"F","minutesPlayed":57,"expectedGoals":0.1408,"expectedAssists":0.0851225,"goals":1,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":1,"rating":7.7},
        {"id":988656,"name":"Gustavo Caballero","position":"F","minutesPlayed":65,"expectedGoals":0.0511,"expectedAssists":0.00772936,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.8},
        {"id":986233,"name":"Mauricio","position":"M","minutesPlayed":63,"expectedGoals":0,"expectedAssists":0.126125,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":7.7},
        {"id":805427,"name":"Gustavo Velázquez","position":"D","minutesPlayed":30,"expectedGoals":0,"expectedAssists":0.00580852,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":883206,"name":"Braian Ojeda","position":"M","minutesPlayed":21,"expectedGoals":0,"expectedAssists":0.0247606,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
    ],
    12812998: [
        {"id":994363,"name":"Bart Verbruggen","position":"G","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.00226976,"goals":0,"goalAssist":0,"saves":5,"totalShots":0,"keyPass":0,"rating":8.3},
        {"id":962012,"name":"Jan Paul van Hecke","position":"D","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.0334697,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.8},
        {"id":151545,"name":"Virgil van Dijk","position":"D","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.0115574,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.0},
        {"id":149663,"name":"Nathan Aké","position":"D","minutesPlayed":71,"expectedGoals":0,"expectedAssists":0.00492341,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":759520,"name":"Denzel Dumfries","position":"M","minutesPlayed":120,"expectedGoals":0.0095,"expectedAssists":0.0110268,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.3},
        {"id":904897,"name":"Ryan Gravenberch","position":"M","minutesPlayed":86,"expectedGoals":0.0958,"expectedAssists":0.0101174,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.5},
        {"id":795222,"name":"Frenkie de Jong","position":"M","minutesPlayed":110,"expectedGoals":0,"expectedAssists":0.0398092,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":998247,"name":"Micky van de Ven","position":"D","minutesPlayed":86,"expectedGoals":0.0382,"expectedAssists":0.00147499,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.6},
        {"id":917005,"name":"Crysencio Summerville","position":"F","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.138902,"goals":0,"goalAssist":1,"saves":0,"totalShots":0,"keyPass":3,"rating":6.5},
        {"id":862967,"name":"Cody Gakpo","position":"F","minutesPlayed":113,"expectedGoals":0.0956,"expectedAssists":0.00379377,"goals":1,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.9},
        {"id":910048,"name":"Brian Brobbey","position":"F","minutesPlayed":71,"expectedGoals":0,"expectedAssists":0.0401449,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":803033,"name":"Teun Koopmeiners","position":"M","minutesPlayed":49,"expectedGoals":0,"expectedAssists":0.0127411,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.2},
        {"id":252215,"name":"Wout Weghorst","position":"F","minutesPlayed":49,"expectedGoals":0,"expectedAssists":0.0204054,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":7.5},
        {"id":1153079,"name":"Jorrel Hato","position":"D","minutesPlayed":34,"expectedGoals":0,"expectedAssists":0.0627724,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":959805,"name":"Quinten Timber","position":"M","minutesPlayed":34,"expectedGoals":0,"expectedAssists":0.00787309,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.0},
        {"id":100389,"name":"Marten de Roon","position":"M","minutesPlayed":10,"expectedGoals":0,"expectedAssists":0.00335224,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":851596,"name":"Justin Kluivert","position":"F","minutesPlayed":8,"expectedGoals":0,"expectedAssists":0.0000335,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.2},
        {"id":360938,"name":"Yassine Bounou","position":"G","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.0002169,"goals":0,"goalAssist":0,"saves":1,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":814594,"name":"Achraf Hakimi","position":"D","minutesPlayed":120,"expectedGoals":0.2339,"expectedAssists":0.271591,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":3,"rating":6.3},
        {"id":825719,"name":"Issa Diop","position":"D","minutesPlayed":120,"expectedGoals":0.1783,"expectedAssists":0.00623413,"goals":1,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.5},
        {"id":1064218,"name":"Chadi Riad","position":"D","minutesPlayed":75,"expectedGoals":0,"expectedAssists":0.00402461,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.4},
        {"id":847030,"name":"Noussair Mazraoui","position":"D","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.0173278,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.6},
        {"id":1564180,"name":"Ayyoub Bouaddi","position":"M","minutesPlayed":79,"expectedGoals":0.0651,"expectedAssists":0.00815217,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.9},
        {"id":1128530,"name":"Neil El Aynaoui","position":"M","minutesPlayed":120,"expectedGoals":0.0857,"expectedAssists":0.123387,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.1},
        {"id":835485,"name":"Brahim Díaz","position":"M","minutesPlayed":79,"expectedGoals":0,"expectedAssists":0.0721507,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":991421,"name":"Azzedine Ounahi","position":"M","minutesPlayed":86,"expectedGoals":0.0336,"expectedAssists":0.399268,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":3,"rating":7.2},
        {"id":1126569,"name":"Bilal El Khannouss","position":"M","minutesPlayed":87,"expectedGoals":0.0178,"expectedAssists":0.0210679,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":5.7},
        {"id":1063767,"name":"Ismael Saibari","position":"F","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.375303,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":6.4},
        {"id":961684,"name":"Anass Salah-Eddine","position":"D","minutesPlayed":45,"expectedGoals":0.0223,"expectedAssists":0.00858815,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.0},
        {"id":1638338,"name":"Gessime Yassine","position":"F","minutesPlayed":41,"expectedGoals":0,"expectedAssists":0.0127403,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":1605921,"name":"Samir El Mourabet","position":"M","minutesPlayed":41,"expectedGoals":0,"expectedAssists":0.020885,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":953995,"name":"Soufiane Rahimi","position":"F","minutesPlayed":34,"expectedGoals":0.7439,"expectedAssists":0.00405028,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.4},
        {"id":1142675,"name":"Chemsdine Talbi","position":"F","minutesPlayed":33,"expectedGoals":0,"expectedAssists":0.116045,"goals":0,"goalAssist":1,"saves":0,"totalShots":0,"keyPass":1,"rating":7.4},
    ],
    12812995: [
        {"id":191210,"name":"Mike Maignan","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00031703,"goals":0,"goalAssist":0,"saves":3,"totalShots":0,"keyPass":0,"rating":7.7},
        {"id":827212,"name":"Jules Koundé","position":"D","minutesPlayed":75,"expectedGoals":0.0391,"expectedAssists":0.239135,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.1},
        {"id":798583,"name":"Dayot Upamecano","position":"D","minutesPlayed":90,"expectedGoals":0.1305,"expectedAssists":0.010801,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":7.0},
        {"id":941168,"name":"William Saliba","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00671902,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.2},
        {"id":96538,"name":"Lucas Digne","position":"D","minutesPlayed":78,"expectedGoals":0.0154,"expectedAssists":0.0171788,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.1},
        {"id":859025,"name":"Aurélien Tchouaméni","position":"M","minutesPlayed":90,"expectedGoals":0.0235,"expectedAssists":0.132885,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":2,"rating":7.6},
        {"id":250737,"name":"Adrien Rabiot","position":"M","minutesPlayed":90,"expectedGoals":0.0603,"expectedAssists":0.146934,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":3,"rating":6.9},
        {"id":818244,"name":"Ousmane Dembélé","position":"F","minutesPlayed":75,"expectedGoals":0.2467,"expectedAssists":0.0950154,"goals":0,"goalAssist":1,"saves":0,"totalShots":2,"keyPass":4,"rating":7.4},
        {"id":978838,"name":"Michael Olise","position":"M","minutesPlayed":85,"expectedGoals":0.8643,"expectedAssists":0.773205,"goals":0,"goalAssist":2,"saves":0,"totalShots":6,"keyPass":3,"rating":8.8},
        {"id":996952,"name":"Bradley Barcola","position":"F","minutesPlayed":90,"expectedGoals":0.9994,"expectedAssists":0.0343335,"goals":1,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":1,"rating":7.9},
        {"id":826643,"name":"Kylian Mbappé","position":"F","minutesPlayed":85,"expectedGoals":0.5974,"expectedAssists":0.0984948,"goals":2,"goalAssist":0,"saves":0,"totalShots":5,"keyPass":4,"rating":9.8},
        {"id":996958,"name":"Malo Gusto","position":"D","minutesPlayed":15,"expectedGoals":0,"expectedAssists":0.00242832,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.7},
        {"id":1154605,"name":"Désiré Doué","position":"F","minutesPlayed":15,"expectedGoals":0.0368,"expectedAssists":0.0767471,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.7},
        {"id":788027,"name":"Theo Hernández","position":"D","minutesPlayed":12,"expectedGoals":0,"expectedAssists":0.00565967,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.9},
        {"id":979128,"name":"Rayan Cherki","position":"M","minutesPlayed":9,"expectedGoals":0,"expectedAssists":0.00050723,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":848276,"name":"Jean-Philippe Mateta","position":"F","minutesPlayed":9,"expectedGoals":0.2546,"expectedAssists":0.00000169,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.3},
        {"id":978728,"name":"Jacob Widell Zetterström","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00074923,"goals":0,"goalAssist":0,"saves":9,"totalShots":0,"keyPass":0,"rating":8.2},
        {"id":1021272,"name":"Daniel Svensson","position":"D","minutesPlayed":82,"expectedGoals":0,"expectedAssists":0.0686185,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":5.9},
        {"id":965263,"name":"Gustaf Lagerbielke","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00478396,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.4},
        {"id":143334,"name":"Victor Lindelöf","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0320169,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":834308,"name":"Gabriel Gudmundsson","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0102405,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.2},
        {"id":979232,"name":"Anthony Elanga","position":"F","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0671249,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.4},
        {"id":1391251,"name":"Lucas Bergvall","position":"M","minutesPlayed":66,"expectedGoals":0.0364,"expectedAssists":0.0161832,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.7},
        {"id":1036269,"name":"Yasin Ayari","position":"M","minutesPlayed":82,"expectedGoals":0,"expectedAssists":0.0597933,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.6},
        {"id":1383695,"name":"Elliot Stroud","position":"M","minutesPlayed":66,"expectedGoals":0.1108,"expectedAssists":0.00087019,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.5},
        {"id":804508,"name":"Viktor Gyökeres","position":"F","minutesPlayed":90,"expectedGoals":0.2612,"expectedAssists":0.0219831,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.9},
        {"id":823941,"name":"Alexander Isak","position":"F","minutesPlayed":89,"expectedGoals":0.1702,"expectedAssists":0.00582951,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.2},
        {"id":1173223,"name":"Besfort Zeneli","position":"M","minutesPlayed":24,"expectedGoals":0,"expectedAssists":0.00807432,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":1022820,"name":"Taha Abdi Ali","position":"M","minutesPlayed":24,"expectedGoals":0,"expectedAssists":0.0108642,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":796987,"name":"Mattias Svanberg","position":"M","minutesPlayed":8,"expectedGoals":0.0858,"expectedAssists":0.0074339,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.8},
        {"id":918517,"name":"Benjamin Nygren","position":"F","minutesPlayed":8,"expectedGoals":0,"expectedAssists":0.0455921,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.6},
    ],
    12813001: [
        {"id":990408,"name":"Raúl Rangel","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00179188,"goals":0,"goalAssist":0,"saves":1,"totalShots":0,"keyPass":0,"rating":7.6},
        {"id":832868,"name":"Jorge Sánchez","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.042408,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":7.0},
        {"id":818406,"name":"César Montes","position":"D","minutesPlayed":90,"expectedGoals":0.089,"expectedAssists":0.00232875,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.7},
        {"id":889785,"name":"Johan Vásquez","position":"D","minutesPlayed":90,"expectedGoals":0.101,"expectedAssists":0.00514174,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.6},
        {"id":770253,"name":"Jesús Gallardo","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0035134,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":1914576,"name":"Gilberto Mora","position":"M","minutesPlayed":58,"expectedGoals":0.0798,"expectedAssists":0.145041,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":2,"rating":7.3},
        {"id":944068,"name":"Erik Lira","position":"M","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0388503,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":7.1},
        {"id":1172773,"name":"Luis Romo","position":"M","minutesPlayed":73,"expectedGoals":0.0226,"expectedAssists":0.135684,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.8},
        {"id":865500,"name":"Roberto Alvarado","position":"F","minutesPlayed":80,"expectedGoals":0.1351,"expectedAssists":0.318526,"goals":0,"goalAssist":1,"saves":0,"totalShots":3,"keyPass":4,"rating":7.2},
        {"id":192442,"name":"Raúl Jiménez","position":"F","minutesPlayed":74,"expectedGoals":0.459,"expectedAssists":0.0301025,"goals":1,"goalAssist":0,"saves":0,"totalShots":4,"keyPass":0,"rating":7.7},
        {"id":843114,"name":"Julián Quiñones","position":"F","minutesPlayed":80,"expectedGoals":0.0997,"expectedAssists":0.0433667,"goals":1,"goalAssist":1,"saves":0,"totalShots":1,"keyPass":3,"rating":8.2},
        {"id":1023088,"name":"Brian Gutiérrez","position":"M","minutesPlayed":32,"expectedGoals":0,"expectedAssists":0.0,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":1119345,"name":"Obed Vargas","position":"M","minutesPlayed":17,"expectedGoals":0,"expectedAssists":0.00089945,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":892141,"name":"Santiago Giménez","position":"F","minutesPlayed":16,"expectedGoals":0,"expectedAssists":0.0501302,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.0},
        {"id":989236,"name":"Israel Reyes","position":"D","minutesPlayed":10,"expectedGoals":0,"expectedAssists":0.00074652,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":850404,"name":"Orbellín Pineda","position":"M","minutesPlayed":10,"expectedGoals":0.0649,"expectedAssists":0.0002602,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.3},
        {"id":588618,"name":"Hernán Galíndez","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00229183,"goals":0,"goalAssist":0,"saves":1,"totalShots":0,"keyPass":0,"rating":6.4},
        {"id":822729,"name":"Alan Franco","position":"D","minutesPlayed":45,"expectedGoals":0,"expectedAssists":0.00450087,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":5.9},
        {"id":1187275,"name":"Joel Ordóñez","position":"D","minutesPlayed":45,"expectedGoals":0,"expectedAssists":0.00024159,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":5.5},
        {"id":979480,"name":"Willian Pacho","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00695416,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.8},
        {"id":1002837,"name":"Piero Hincapié","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0823355,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.5},
        {"id":879802,"name":"John Yeboah","position":"M","minutesPlayed":79,"expectedGoals":0.1623,"expectedAssists":0.0124236,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":7.2},
        {"id":987650,"name":"Moisés Caicedo","position":"M","minutesPlayed":90,"expectedGoals":0.0087,"expectedAssists":0.180364,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.3},
        {"id":1002524,"name":"Pedro Vite","position":"M","minutesPlayed":90,"expectedGoals":0.0227,"expectedAssists":0.0466411,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.7},
        {"id":1116571,"name":"Nilson Angulo","position":"M","minutesPlayed":79,"expectedGoals":0,"expectedAssists":0.0705123,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":937937,"name":"Gonzalo Plata","position":"F","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0540602,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.5},
        {"id":106456,"name":"Enner Valencia","position":"F","minutesPlayed":59,"expectedGoals":0,"expectedAssists":0.0,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.0},
        {"id":1106546,"name":"Yaimar Medina","position":"D","minutesPlayed":45,"expectedGoals":0.0221,"expectedAssists":0.0263606,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.6},
        {"id":881844,"name":"Ángelo Preciado","position":"D","minutesPlayed":45,"expectedGoals":0,"expectedAssists":0.00834489,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.3},
        {"id":1431770,"name":"Kevin Rodriguez","position":"F","minutesPlayed":31,"expectedGoals":0.421,"expectedAssists":0.0027504,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.4},
        {"id":1464025,"name":"Kendry Páez","position":"M","minutesPlayed":11,"expectedGoals":0,"expectedAssists":0.0604226,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.8},
        {"id":804770,"name":"Jordy Caicedo","position":"F","minutesPlayed":11,"expectedGoals":0.1151,"expectedAssists":0.00245053,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.2},
    ],
    12812989: [
        {"id":877977,"name":"Yahia Fofana","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00059576,"goals":0,"goalAssist":0,"saves":1,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":1002033,"name":"Guéla Doué","position":"D","minutesPlayed":90,"expectedGoals":0.1292,"expectedAssists":0.184337,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.7},
        {"id":973437,"name":"Odilon Kossounou","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00552577,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":1013842,"name":"Emmanuel Agbadou","position":"D","minutesPlayed":90,"expectedGoals":0.1032,"expectedAssists":0.00722085,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":0,"rating":7.0},
        {"id":831781,"name":"Ghislain Konan","position":"D","minutesPlayed":89,"expectedGoals":0.1391,"expectedAssists":0.0265466,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.4},
        {"id":843754,"name":"Ibrahim Sangaré","position":"M","minutesPlayed":90,"expectedGoals":0.0191,"expectedAssists":0.0471953,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.6},
        {"id":593526,"name":"Nicolas Pépé","position":"F","minutesPlayed":87,"expectedGoals":0.3771,"expectedAssists":0.26375,"goals":0,"goalAssist":1,"saves":0,"totalShots":2,"keyPass":3,"rating":6.8},
        {"id":359226,"name":"Franck Kessié","position":"M","minutesPlayed":90,"expectedGoals":0.1001,"expectedAssists":0.0287891,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.5},
        {"id":1888002,"name":"Christ Inao Oulaï","position":"M","minutesPlayed":60,"expectedGoals":0,"expectedAssists":0.0333033,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":6.9},
        {"id":2087085,"name":"Yan Diomande","position":"F","minutesPlayed":89,"expectedGoals":0.1683,"expectedAssists":0.239361,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.3},
        {"id":1086223,"name":"Ange-Yoan Bonny","position":"F","minutesPlayed":60,"expectedGoals":0,"expectedAssists":0.507153,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.1},
        {"id":971037,"name":"Amad Diallo","position":"F","minutesPlayed":30,"expectedGoals":0.2324,"expectedAssists":0.246963,"goals":1,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":1,"rating":9.5},
        {"id":979315,"name":"Elye Wahi","position":"F","minutesPlayed":30,"expectedGoals":0,"expectedAssists":0.02571,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":1188191,"name":"Oumar Diakité","position":"F","minutesPlayed":11,"expectedGoals":0,"expectedAssists":0.00696951,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":22209,"name":"Ørjan Nyland","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00185115,"goals":0,"goalAssist":0,"saves":4,"totalShots":0,"keyPass":0,"rating":7.8},
        {"id":934409,"name":"Marcus Pedersen","position":"D","minutesPlayed":83,"expectedGoals":0,"expectedAssists":0.0530424,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.1},
        {"id":576384,"name":"Kristoffer Ajer","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00637219,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.6},
        {"id":933264,"name":"Torbjørn Heggem","position":"D","minutesPlayed":90,"expectedGoals":0.3842,"expectedAssists":0.00617604,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.7},
        {"id":1031283,"name":"David Møller Wolfe","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0138404,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.0},
        {"id":547410,"name":"Martin Ødegaard","position":"M","minutesPlayed":90,"expectedGoals":0.0281,"expectedAssists":0.229998,"goals":0,"goalAssist":1,"saves":0,"totalShots":1,"keyPass":1,"rating":7.2},
        {"id":793167,"name":"Sander Berge","position":"M","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0202965,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":355174,"name":"Patrick Berg","position":"M","minutesPlayed":90,"expectedGoals":0,"expectedAssists":1.05178,"goals":0,"goalAssist":1,"saves":0,"totalShots":0,"keyPass":2,"rating":8.0},
        {"id":309078,"name":"Alexander Sørloth","position":"F","minutesPlayed":71,"expectedGoals":0.2317,"expectedAssists":0.886116,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":2,"rating":6.8},
        {"id":839956,"name":"Erling Haaland","position":"F","minutesPlayed":90,"expectedGoals":1.1677,"expectedAssists":0.0101483,"goals":1,"goalAssist":0,"saves":0,"totalShots":4,"keyPass":1,"rating":7.4},
        {"id":1121923,"name":"Antonio Nusa","position":"F","minutesPlayed":71,"expectedGoals":0.0218,"expectedAssists":0.0401362,"goals":1,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.3},
        {"id":1100952,"name":"Andreas Schjelderup","position":"F","minutesPlayed":19,"expectedGoals":0.0697,"expectedAssists":0.028618,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.4},
        {"id":1065216,"name":"Oscar Bobb","position":"M","minutesPlayed":19,"expectedGoals":0,"expectedAssists":0.237409,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.6},
        {"id":228364,"name":"Fredrik Aursnes","position":"M","minutesPlayed":15,"expectedGoals":0,"expectedAssists":0.00267904,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
    ],
    12813013: [
        {"id":70988,"name":"Thibaut Courtois","position":"G","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.00632507,"goals":0,"goalAssist":0,"saves":3,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":329417,"name":"Timothy Castagne","position":"D","minutesPlayed":120,"expectedGoals":0.0636,"expectedAssists":0.134766,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":2,"rating":6.7},
        {"id":248331,"name":"Brandon Mechele","position":"D","minutesPlayed":120,"expectedGoals":0.0656,"expectedAssists":0.0201907,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":2,"rating":6.7},
        {"id":965778,"name":"Arthur Theate","position":"D","minutesPlayed":120,"expectedGoals":0.0211,"expectedAssists":0.0216495,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":7.1},
        {"id":997152,"name":"Maxim De Cuyper","position":"D","minutesPlayed":78,"expectedGoals":0.0511,"expectedAssists":0.0212175,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.2},
        {"id":331737,"name":"Youri Tielemans","position":"M","minutesPlayed":120,"expectedGoals":0.9831,"expectedAssists":0.032054,"goals":2,"goalAssist":0,"saves":0,"totalShots":4,"keyPass":1,"rating":8.6},
        {"id":118085,"name":"Hans Vanaken","position":"M","minutesPlayed":63,"expectedGoals":0,"expectedAssists":0.0668191,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":135666,"name":"Leandro Trossard","position":"M","minutesPlayed":109,"expectedGoals":0.0969,"expectedAssists":0.420633,"goals":0,"goalAssist":1,"saves":0,"totalShots":2,"keyPass":3,"rating":7.5},
        {"id":70996,"name":"Kevin De Bruyne","position":"M","minutesPlayed":56,"expectedGoals":0.0503,"expectedAssists":0.0263635,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":1,"rating":6.7},
        {"id":934386,"name":"Jérémy Doku","position":"M","minutesPlayed":56,"expectedGoals":0,"expectedAssists":0.0442414,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":960441,"name":"Charles De Ketelaere","position":"F","minutesPlayed":45,"expectedGoals":0,"expectedAssists":0.0221856,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.3},
        {"id":78893,"name":"Romelu Lukaku","position":"F","minutesPlayed":75,"expectedGoals":0.1589,"expectedAssists":0.134289,"goals":1,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":2,"rating":7.5},
        {"id":889378,"name":"Nicolas Raskin","position":"M","minutesPlayed":64,"expectedGoals":0.0515,"expectedAssists":0.137028,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.0},
        {"id":823631,"name":"Dodi Lukebakio","position":"M","minutesPlayed":64,"expectedGoals":0.1858,"expectedAssists":0.135517,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":1,"rating":7.0},
        {"id":1142233,"name":"Diego Moreira","position":"F","minutesPlayed":57,"expectedGoals":0,"expectedAssists":0.0186504,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":128587,"name":"Thomas Meunier","position":"D","minutesPlayed":42,"expectedGoals":0.0161,"expectedAssists":0.275209,"goals":0,"goalAssist":1,"saves":0,"totalShots":1,"keyPass":2,"rating":7.1},
        {"id":923973,"name":"Amadou Onana","position":"M","minutesPlayed":11,"expectedGoals":0,"expectedAssists":0.00443558,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":580226,"name":"Mory Diaw","position":"G","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.00134311,"goals":0,"goalAssist":0,"saves":3,"totalShots":0,"keyPass":0,"rating":6.0},
        {"id":873534,"name":"Krépin Diatta","position":"M","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.068148,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":913679,"name":"Pathé Ismaël Ciss","position":"M","minutesPlayed":120,"expectedGoals":0.0835,"expectedAssists":0.0150059,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.8},
        {"id":758168,"name":"Moussa Niakhate","position":"D","minutesPlayed":120,"expectedGoals":0,"expectedAssists":0.234591,"goals":0,"goalAssist":1,"saves":0,"totalShots":0,"keyPass":2,"rating":6.6},
        {"id":897291,"name":"Ismail Jakobs","position":"D","minutesPlayed":94,"expectedGoals":0,"expectedAssists":0.0174539,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.1},
        {"id":1128532,"name":"Habib Diarra","position":"M","minutesPlayed":73,"expectedGoals":1.0116,"expectedAssists":0.0257459,"goals":1,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":1,"rating":7.4},
        {"id":106337,"name":"Idrissa Gana Gueye","position":"M","minutesPlayed":96,"expectedGoals":0.0657,"expectedAssists":0.0268268,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.7},
        {"id":879694,"name":"Pape Gueye","position":"M","minutesPlayed":66,"expectedGoals":0.0695,"expectedAssists":0.0305883,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.2},
        {"id":914309,"name":"Iliman Ndiaye","position":"F","minutesPlayed":73,"expectedGoals":0.1014,"expectedAssists":0.0159057,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.8},
        {"id":845286,"name":"Ismaïla Sarr","position":"F","minutesPlayed":120,"expectedGoals":1.5974,"expectedAssists":0.157302,"goals":1,"goalAssist":0,"saves":0,"totalShots":5,"keyPass":2,"rating":8.2},
        {"id":217704,"name":"Sadio Mané","position":"M","minutesPlayed":94,"expectedGoals":0.0391,"expectedAssists":0.410712,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":3,"rating":7.0},
        {"id":1389846,"name":"Lamine Camara","position":"M","minutesPlayed":54,"expectedGoals":0,"expectedAssists":0.0209525,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":5.7},
        {"id":1002711,"name":"Pape Matar Sarr","position":"M","minutesPlayed":47,"expectedGoals":0.1997,"expectedAssists":0.0252014,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.4},
        {"id":1590918,"name":"Ibrahim Mbaye","position":"F","minutesPlayed":47,"expectedGoals":0.5165,"expectedAssists":0.0338631,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":2,"rating":6.5},
        {"id":1471764,"name":"El Hadji Malick Diouf","position":"D","minutesPlayed":26,"expectedGoals":0,"expectedAssists":0.0255004,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.3},
        {"id":1085381,"name":"Nicolas Jackson","position":"F","minutesPlayed":26,"expectedGoals":0,"expectedAssists":0.0266129,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":2427970,"name":"Bara Sapoko Ndiaye","position":"M","minutesPlayed":24,"expectedGoals":0.0306,"expectedAssists":0.141827,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.6},
    ],
    12812992: [
        {"id":973436,"name":"Matthew Freese","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00038734,"goals":0,"goalAssist":0,"saves":3,"totalShots":0,"keyPass":0,"rating":7.0},
        {"id":1184541,"name":"Alexander Freeman","position":"D","minutesPlayed":90,"expectedGoals":0.0402,"expectedAssists":0.0270589,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.5},
        {"id":931844,"name":"Chris Richards","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00547078,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.4},
        {"id":118179,"name":"Tim Ream","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0140486,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":7.4},
        {"id":803174,"name":"Antonee Robinson","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.115046,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":7.5},
        {"id":881931,"name":"Weston McKennie","position":"M","minutesPlayed":89,"expectedGoals":0,"expectedAssists":0.260972,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":7.4},
        {"id":800419,"name":"Tyler Adams","position":"M","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0627019,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":975798,"name":"Malik Tillman","position":"M","minutesPlayed":90,"expectedGoals":0.1925,"expectedAssists":0.115758,"goals":1,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":1,"rating":8.0},
        {"id":906021,"name":"Sergino Dest","position":"F","minutesPlayed":87,"expectedGoals":0,"expectedAssists":0.225237,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":7.3},
        {"id":934237,"name":"Folarin Balogun","position":"F","minutesPlayed":64,"expectedGoals":0.5653,"expectedAssists":0.0125914,"goals":1,"goalAssist":0,"saves":0,"totalShots":4,"keyPass":0,"rating":6.2},
        {"id":817957,"name":"Christian Pulisic","position":"F","minutesPlayed":88,"expectedGoals":0.0869,"expectedAssists":0.0190227,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.9},
        {"id":1014845,"name":"Sebastian Berhalter","position":"M","minutesPlayed":13,"expectedGoals":0,"expectedAssists":0.0028071,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":986395,"name":"Ricardo Pepi","position":"F","minutesPlayed":12,"expectedGoals":0,"expectedAssists":0.00139327,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.4},
        {"id":325061,"name":"Nikola Vasilj","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00097636,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":5.3},
        {"id":1102791,"name":"Amar Dedic","position":"D","minutesPlayed":90,"expectedGoals":0.0169,"expectedAssists":0.00787859,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.7},
        {"id":831488,"name":"Nikola Katic","position":"D","minutesPlayed":75,"expectedGoals":0.0154,"expectedAssists":0.00202895,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.2},
        {"id":1118177,"name":"Tarik Muharemovic","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.012328,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":843746,"name":"Stjepan Radeljic","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0151689,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.4},
        {"id":142148,"name":"Sead Kolasinac","position":"D","minutesPlayed":75,"expectedGoals":0,"expectedAssists":0.00495655,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.3},
        {"id":988893,"name":"Armin Gigovic","position":"M","minutesPlayed":51,"expectedGoals":0,"expectedAssists":0.00027747,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":283833,"name":"Ivan Sunjic","position":"M","minutesPlayed":51,"expectedGoals":0,"expectedAssists":0.0028457,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.3},
        {"id":1425366,"name":"Kerim Alajbegovic","position":"M","minutesPlayed":90,"expectedGoals":0.051,"expectedAssists":0.0177723,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.0},
        {"id":14990,"name":"Edin Dzeko","position":"F","minutesPlayed":51,"expectedGoals":0,"expectedAssists":0.0281038,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.5},
        {"id":878081,"name":"Ermedin Demirovic","position":"F","minutesPlayed":90,"expectedGoals":0.0916,"expectedAssists":0.00095541,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.2},
        {"id":1102659,"name":"Benjamin Tahirovic","position":"M","minutesPlayed":39,"expectedGoals":0,"expectedAssists":0.0230826,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.6},
        {"id":1149353,"name":"Ermin Mahmic","position":"M","minutesPlayed":39,"expectedGoals":0.0407,"expectedAssists":0.00429551,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.0},
        {"id":1136110,"name":"Esmir Bajraktarevic","position":"F","minutesPlayed":39,"expectedGoals":0.0182,"expectedAssists":0.0142166,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":2,"rating":6.5},
        {"id":1129610,"name":"Amar Memic","position":"M","minutesPlayed":15,"expectedGoals":0.0203,"expectedAssists":0.00210012,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.2},
    ],
    12813020: [
        {"id":138530,"name":"Jordan Pickford","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00087241,"goals":0,"goalAssist":0,"saves":1,"totalShots":0,"keyPass":0,"rating":5.7},
        {"id":945798,"name":"Djed Spence","position":"D","minutesPlayed":70,"expectedGoals":0,"expectedAssists":0.0113324,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":827679,"name":"Ezri Konsa","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0244425,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":877994,"name":"Marc Guéhi","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0255483,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.1},
        {"id":1142703,"name":"Nico O'Reilly","position":"D","minutesPlayed":90,"expectedGoals":0.4396,"expectedAssists":0.0231393,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":5.9},
        {"id":994546,"name":"Elliot Anderson","position":"M","minutesPlayed":90,"expectedGoals":0.0374,"expectedAssists":0.223711,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":3,"rating":7.6},
        {"id":856714,"name":"Declan Rice","position":"M","minutesPlayed":89,"expectedGoals":0,"expectedAssists":0.297612,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":7.1},
        {"id":966547,"name":"Noni Madueke","position":"F","minutesPlayed":61,"expectedGoals":0.0351,"expectedAssists":0.845881,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":3,"rating":8.0},
        {"id":991011,"name":"Jude Bellingham","position":"M","minutesPlayed":90,"expectedGoals":0.6575,"expectedAssists":0.292626,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":2,"rating":7.0},
        {"id":814590,"name":"Marcus Rashford","position":"F","minutesPlayed":61,"expectedGoals":0.4112,"expectedAssists":0.0417866,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":0,"rating":6.9},
        {"id":108579,"name":"Harry Kane","position":"F","minutesPlayed":90,"expectedGoals":0.5426,"expectedAssists":0.0173374,"goals":2,"goalAssist":0,"saves":0,"totalShots":5,"keyPass":1,"rating":8.5},
        {"id":914902,"name":"Anthony Gordon","position":"F","minutesPlayed":29,"expectedGoals":0.0349,"expectedAssists":0.24658,"goals":0,"goalAssist":2,"saves":0,"totalShots":1,"keyPass":2,"rating":7.1},
        {"id":934235,"name":"Bukayo Saka","position":"F","minutesPlayed":29,"expectedGoals":0,"expectedAssists":0.0151278,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":864921,"name":"Eberechi Eze","position":"M","minutesPlayed":20,"expectedGoals":0,"expectedAssists":0.0128544,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":599192,"name":"Lionel Mpasi Nzau","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00062663,"goals":0,"goalAssist":0,"saves":5,"totalShots":0,"keyPass":0,"rating":7.6},
        {"id":863653,"name":"Aaron Wan-Bissaka","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00717912,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.6},
        {"id":238612,"name":"Chancel Mbemba","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0174667,"goals":0,"goalAssist":1,"saves":0,"totalShots":0,"keyPass":1,"rating":7.2},
        {"id":817979,"name":"Axel Tuanzebe","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00336084,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":174975,"name":"Arthur Masuaku","position":"D","minutesPlayed":89,"expectedGoals":0,"expectedAssists":0.00609324,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.3},
        {"id":1391541,"name":"Ngal'ayel Mukau","position":"M","minutesPlayed":76,"expectedGoals":0,"expectedAssists":0.00462091,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
        {"id":892624,"name":"Samuel Moutoussamy","position":"M","minutesPlayed":89,"expectedGoals":0,"expectedAssists":0.0135137,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.0},
        {"id":1171539,"name":"Noah Sadiki","position":"M","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00857882,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.3},
        {"id":963399,"name":"Nathanaël Mbuku","position":"M","minutesPlayed":64,"expectedGoals":0.017,"expectedAssists":0.0165182,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.9},
        {"id":805123,"name":"Yoane Wissa","position":"F","minutesPlayed":90,"expectedGoals":0.6233,"expectedAssists":0.00540861,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.5},
        {"id":1160969,"name":"Brian Cipenga","position":"F","minutesPlayed":76,"expectedGoals":0.1033,"expectedAssists":0.0124936,"goals":1,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":1,"rating":7.0},
        {"id":862078,"name":"Meschak Elia","position":"F","minutesPlayed":26,"expectedGoals":0.0288,"expectedAssists":0.00121018,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.4},
        {"id":344953,"name":"Théo Bongonda","position":"M","minutesPlayed":14,"expectedGoals":0,"expectedAssists":0.00154737,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":917305,"name":"Edo Kayembe","position":"M","minutesPlayed":14,"expectedGoals":0,"expectedAssists":0.00648675,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
    ],
    12813004: [
        {"id":797291,"name":"Unai Simón","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0001251,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.9},
        {"id":913654,"name":"Pedro Porro","position":"D","minutesPlayed":90,"expectedGoals":0.5267,"expectedAssists":0.0979161,"goals":1,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":5,"rating":8.4},
        {"id":1402913,"name":"Pau Cubarsí","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0224229,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":7.9},
        {"id":149734,"name":"Aymeric Laporte","position":"D","minutesPlayed":89,"expectedGoals":0.1922,"expectedAssists":0.0154117,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":7.8},
        {"id":794939,"name":"Marc Cucurella","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.368317,"goals":0,"goalAssist":2,"saves":0,"totalShots":0,"keyPass":2,"rating":8.3},
        {"id":827606,"name":"Rodri","position":"M","minutesPlayed":90,"expectedGoals":0.0204,"expectedAssists":0.0257032,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":2,"rating":7.5},
        {"id":992587,"name":"Pedri","position":"M","minutesPlayed":89,"expectedGoals":0,"expectedAssists":0.118338,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":7.2},
        {"id":1402912,"name":"Lamine Yamal","position":"M","minutesPlayed":85,"expectedGoals":0.719,"expectedAssists":0.154516,"goals":0,"goalAssist":0,"saves":0,"totalShots":6,"keyPass":2,"rating":7.3},
        {"id":789071,"name":"Dani Olmo","position":"M","minutesPlayed":71,"expectedGoals":0.155,"expectedAssists":0.11711,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":2,"rating":7.1},
        {"id":910031,"name":"Alex Baena","position":"M","minutesPlayed":71,"expectedGoals":0.0481,"expectedAssists":0.727047,"goals":0,"goalAssist":1,"saves":0,"totalShots":2,"keyPass":5,"rating":8.3},
        {"id":823622,"name":"Mikel Oyarzabal","position":"F","minutesPlayed":90,"expectedGoals":1.0858,"expectedAssists":0.0294876,"goals":2,"goalAssist":0,"saves":0,"totalShots":6,"keyPass":0,"rating":9.2},
        {"id":592010,"name":"Mikel Merino","position":"M","minutesPlayed":19,"expectedGoals":0,"expectedAssists":0.00821507,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":855833,"name":"Ferran Torres","position":"F","minutesPlayed":19,"expectedGoals":0.0518,"expectedAssists":0.0210826,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.2},
        {"id":1103693,"name":"Pablo Gavi","position":"M","minutesPlayed":11,"expectedGoals":0,"expectedAssists":0.000058,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
        {"id":282073,"name":"Alexander Schlager","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0000869,"goals":0,"goalAssist":0,"saves":6,"totalShots":0,"keyPass":0,"rating":6.7},
        {"id":355486,"name":"Stefan Posch","position":"D","minutesPlayed":85,"expectedGoals":0.0554,"expectedAssists":0.00437776,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":5.9},
        {"id":794953,"name":"Kevin Danso","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00189708,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":66492,"name":"David Alaba","position":"D","minutesPlayed":90,"expectedGoals":0.0219,"expectedAssists":0.00843584,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.6},
        {"id":355492,"name":"Konrad Laimer","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00988199,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.4},
        {"id":976575,"name":"Nicolas Seiwald","position":"M","minutesPlayed":45,"expectedGoals":0.0664,"expectedAssists":0.00091988,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.5},
        {"id":791079,"name":"Xaver Schlager","position":"M","minutesPlayed":45,"expectedGoals":0,"expectedAssists":0.00126668,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.1},
        {"id":830127,"name":"Romano Schmid","position":"M","minutesPlayed":60,"expectedGoals":0,"expectedAssists":0.107281,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.6},
        {"id":1146018,"name":"Paul Wanner","position":"M","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0263401,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.2},
        {"id":133908,"name":"Marcel Sabitzer","position":"M","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.272456,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":6.8},
        {"id":111483,"name":"Michael Gregoritsch","position":"F","minutesPlayed":60,"expectedGoals":0,"expectedAssists":0.0000189,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.0},
        {"id":994556,"name":"Carney Chukwuemeka","position":"M","minutesPlayed":45,"expectedGoals":0.0592,"expectedAssists":0.0519621,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.2},
        {"id":186719,"name":"Florian Grillitsch","position":"M","minutesPlayed":45,"expectedGoals":0,"expectedAssists":0.00938666,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
        {"id":21927,"name":"Marko Arnautović","position":"F","minutesPlayed":30,"expectedGoals":0,"expectedAssists":0.0433808,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.2},
        {"id":870038,"name":"Saša Kalajdžić","position":"F","minutesPlayed":30,"expectedGoals":0.1194,"expectedAssists":0.0883471,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.2},
    ],
}

# Brazil-Japan already split (home=Brazil, away=Japan)
LINEUPS_SPLIT = {
    12813012: {
        "home": [
            {"id":243609,"name":"Alisson","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00045017,"goals":0,"goalAssist":0,"saves":1,"totalShots":0,"keyPass":0,"rating":6.4},
            {"id":124992,"name":"Danilo","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.176538,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.0},
            {"id":155995,"name":"Marquinhos","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.154558,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":7.8},
            {"id":869792,"name":"Gabriel Magalhães","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.447248,"goals":0,"goalAssist":1,"saves":0,"totalShots":0,"keyPass":2,"rating":7.9},
            {"id":243583,"name":"Douglas Santos","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.342753,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":2,"rating":7.3},
            {"id":866469,"name":"Bruno Guimarães","position":"M","minutesPlayed":89,"expectedGoals":0.2008,"expectedAssists":0.313786,"goals":0,"goalAssist":1,"saves":0,"totalShots":4,"keyPass":4,"rating":7.4},
            {"id":122951,"name":"Casemiro","position":"M","minutesPlayed":89,"expectedGoals":0.6158,"expectedAssists":0.0473903,"goals":1,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":7.9},
            {"id":839981,"name":"Lucas Paquetá","position":"M","minutesPlayed":45,"expectedGoals":0.1201,"expectedAssists":0.0548759,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":2,"rating":6.8},
            {"id":1464966,"name":"Rayan","position":"F","minutesPlayed":90,"expectedGoals":0.0684,"expectedAssists":0.13322,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":2,"rating":7.4},
            {"id":886363,"name":"Matheus Cunha","position":"F","minutesPlayed":66,"expectedGoals":0.1726,"expectedAssists":0.04981,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":0,"rating":6.3},
            {"id":868812,"name":"Vinícius Júnior","position":"F","minutesPlayed":90,"expectedGoals":0.3631,"expectedAssists":0.183904,"goals":0,"goalAssist":0,"saves":0,"totalShots":3,"keyPass":2,"rating":7.5},
            {"id":1174937,"name":"Endrick","position":"F","minutesPlayed":45,"expectedGoals":0.0757,"expectedAssists":0.00960867,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.2},
            {"id":922573,"name":"Gabriel Martinelli","position":"F","minutesPlayed":24,"expectedGoals":0.4654,"expectedAssists":0.0228723,"goals":1,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":1,"rating":7.4},
            {"id":243585,"name":"Fabinho","position":"M","minutesPlayed":8,"expectedGoals":0.0184,"expectedAssists":0.00022416,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":6.6},
        ],
        "away": [
            {"id":905351,"name":"Zion Suzuki","position":"G","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00595561,"goals":0,"goalAssist":0,"saves":4,"totalShots":0,"keyPass":0,"rating":7.0},
            {"id":804434,"name":"Takehiro Tomiyasu","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00665583,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":7.6},
            {"id":386958,"name":"Shogo Taniguchi","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.00517166,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.8},
            {"id":873106,"name":"Hiroki Itō","position":"D","minutesPlayed":90,"expectedGoals":0,"expectedAssists":0.0365536,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.3},
            {"id":790965,"name":"Ritsu Doan","position":"M","minutesPlayed":66,"expectedGoals":0,"expectedAssists":0.0380303,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
            {"id":1028307,"name":"Kaishu Sano","position":"M","minutesPlayed":90,"expectedGoals":0.1222,"expectedAssists":0.0254588,"goals":1,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":0,"rating":7.7},
            {"id":794338,"name":"Daichi Kamada","position":"M","minutesPlayed":78,"expectedGoals":0.0906,"expectedAssists":0.0127317,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.5},
            {"id":905352,"name":"Keito Nakamura","position":"M","minutesPlayed":66,"expectedGoals":0,"expectedAssists":0.00549738,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.5},
            {"id":783278,"name":"Junya Ito","position":"F","minutesPlayed":78,"expectedGoals":0.0252,"expectedAssists":0.0814276,"goals":0,"goalAssist":0,"saves":0,"totalShots":1,"keyPass":1,"rating":6.9},
            {"id":832420,"name":"Daizen Maeda","position":"F","minutesPlayed":89,"expectedGoals":0,"expectedAssists":0.00678906,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":1,"rating":6.8},
            {"id":985823,"name":"Ayase Ueda","position":"F","minutesPlayed":90,"expectedGoals":0.0871,"expectedAssists":0.00171115,"goals":0,"goalAssist":0,"saves":0,"totalShots":2,"keyPass":0,"rating":6.0},
            {"id":905347,"name":"Yukinari Sugawara","position":"D","minutesPlayed":24,"expectedGoals":0,"expectedAssists":0.0019235,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.6},
            {"id":1171902,"name":"Junnosuke Suzuki","position":"D","minutesPlayed":24,"expectedGoals":0,"expectedAssists":0.0000561,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.3},
            {"id":871886,"name":"Ao Tanaka","position":"M","minutesPlayed":12,"expectedGoals":0,"expectedAssists":0.00165023,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.2},
            {"id":925910,"name":"Shuto Machino","position":"F","minutesPlayed":12,"expectedGoals":0,"expectedAssists":0.0010969,"goals":0,"goalAssist":0,"saves":0,"totalShots":0,"keyPass":0,"rating":6.4},
        ],
    }
}


def split_flat(players):
    """Split flat array at second GK."""
    gk_idx = [i for i, p in enumerate(players) if p["position"] == "G"]
    if len(gk_idx) < 2:
        return players, []
    return players[:gk_idx[1]], players[gk_idx[1]:]


def form_stats(matches):
    w_xg = w_xa = total_w = 0.0
    for i, m in enumerate(matches):
        if (m.get("mins") or 0) < 20: continue
        w = (DECAY ** i) * m.get("weight", 1.0)
        mins = m["mins"]
        w_xg    += (m.get("xg", 0) / mins * 90) * w
        w_xa    += (m.get("xa", 0) / mins * 90) * w
        total_w += w
    if total_w == 0: return None
    return {"form_xg_90": round(w_xg / total_w, 4),
            "form_xa_90": round(w_xa / total_w, 4),
            "n": len([m for m in matches if (m.get("mins") or 0) >= 20])}


def process_side(players_list, is_home, tid, eid, player_stats, form_data):
    for p in players_list:
        mins = p.get("minutesPlayed") or 0
        if mins < 5:
            continue
        pid = p["id"]
        xg_raw = p.get("expectedGoals")
        xa_raw = p.get("expectedAssists")
        goals  = p.get("goals") or 0
        xg = float(xg_raw) if xg_raw is not None else max(goals * 0.5, (p.get("totalShots") or 0) * 0.095)
        xa = float(xa_raw) if xa_raw is not None else (p.get("keyPass") or 0) * 0.08

        status = "starter" if mins >= 60 else "sub_in"
        pid_str = str(pid)

        player_stats[pid_str] = {
            "name": p["name"], "mins": mins, "status": status,
            "is_home": is_home, "team_id": tid,
            "goals": goals, "assists": p.get("goalAssist") or 0,
            "yellow": p.get("yellowCards") or 0, "red": p.get("redCards") or 0,
            "rating": p.get("rating"),
            "xg": round(xg, 4), "xa": round(xa, 4),
            "saves": p.get("saves") or 0, "shots": p.get("totalShots") or 0,
            "key_passes": p.get("keyPass") or 0,
        }

        form_entry = {"event_id": eid, "mins": mins,
                      "xg": round(xg, 4), "xa": round(xa, 4),
                      "goals": goals, "weight": WC_WEIGHT}
        fd = form_data.setdefault(pid_str, {"name": p["name"], "team": "", "matches": []})
        existing_eids = {m.get("event_id") for m in fd.get("matches", [])}
        if eid not in existing_eids:
            ms = [form_entry] + fd.get("matches", [])
            fd["matches"] = ms[:N_FORM]
            nf = form_stats(fd["matches"])
            if nf: fd["form"] = nf
            fd["v2"] = True


def main():
    wc_data   = json.load(open(WC_RESULTS, encoding="utf-8"))
    form_data = json.load(open(FORM_PATH,  encoding="utf-8")) if FORM_PATH.exists() else {}

    for eid, meta in MATCH_META.items():
        home, away   = meta["home"], meta["away"]
        home_id, away_id = meta["home_id"], meta["away_id"]
        sh, sa       = meta["sh"], meta["sa"]
        pens         = meta.get("pens")

        print(f"\n[KO] {home} {sh}-{sa} {away}  eid={eid}")

        player_stats = {}

        if eid in LINEUPS_SPLIT:
            sp = LINEUPS_SPLIT[eid]
            process_side(sp["home"], True,  home_id, eid, player_stats, form_data)
            process_side(sp["away"], False, away_id, eid, player_stats, form_data)
        else:
            flat = LINEUPS.get(eid, [])
            home_p, away_p = split_flat(flat)
            process_side(home_p, True,  home_id, eid, player_stats, form_data)
            process_side(away_p, False, away_id, eid, player_stats, form_data)

        # Detect suspensions from red cards
        missing_next = []
        for pid_str, ps in player_stats.items():
            if (ps.get("red") or 0) > 0:
                missing_next.append({
                    "player_id": int(pid_str),
                    "player_name": ps["name"],
                    "team_id": ps["team_id"],
                    "is_home": ps["is_home"],
                    "reason": "suspension"
                })

        h_starters = sum(1 for ps in player_stats.values() if ps["is_home"] and ps["status"] == "starter")
        a_starters = sum(1 for ps in player_stats.values() if not ps["is_home"] and ps["status"] == "starter")
        print(f"    {len(player_stats)} jugadores  (home starters={h_starters}, away starters={a_starters})")

        wc_data.setdefault("matches", {})[str(eid)] = {
            "event_id": eid, "home": home, "away": away,
            "home_id": home_id, "away_id": away_id,
            "group": "KO", "round_num": 4,
            "score_home": sh, "score_away": sa,
            "pens_winner": pens,
            "player_stats": player_stats,
            "incidents": {"goals": [], "cards": [], "missing_next": missing_next},
            "zones": {}, "team_stats": {},
        }

        for m in missing_next:
            print(f"    SUSPENSION: {m['player_name']}")

    json.dump(wc_data,   open(WC_RESULTS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(form_data, open(FORM_PATH,  "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwc_results: {len(wc_data['matches'])} partidos totales")
    print(f"form_data:  {len(form_data)} jugadores")

    for script in ["update_dc_with_f1.py", "build_knockout_bracket.py", "generate_wc_analytics.py"]:
        print(f"\n>>> {script}")
        r = subprocess.run([sys.executable, str(BASE_DIR / script)],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        print((r.stdout or "")[-800:])
        if r.returncode != 0:
            print("ERROR:", (r.stderr or "")[-400:])


if __name__ == "__main__":
    main()
