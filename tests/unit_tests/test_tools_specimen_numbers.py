import pytest

from nmnh_ms_tools.tools.specimen_numbers.parser import Parser




@pytest.mark.parametrize(
    'test_input,expected',
    [
        ('Holotype, US NMNH 4 5 2 6 6 5 , from locality 4', ['NMNH 452665']),
        ('USNM 12345 4', ['USNM 12345']),
        ('NMNH 560-042', ['NMNH 560042']),
        ('USNM El 1732', ['USNM E 11732']),
        ('...internal standard (USNM 113498/1 VG-A99 [12]) were...', ['USNM 113498-1']),
        ('NMNH 113652-53, 113655-60', ['NMNH 113652', 'NMNH 113653', 'NMNH 113655', 'NMNH 113656', 'NMNH 113657', 'NMNH 113658', 'NMNH 113659', 'NMNH 113660']),
        ('USNM Type No. 10660', ['USNM type no. 10660']),
        ('USNM 629a and 629b; 40-44', ['USNM 629A', 'USNM 629B']),
        ('USNM 201 100, 201 lOla-c', ['USNM 201100', 'USNM 201101A', 'USNM 201101B', 'USNM 201101C']),
        ('USNM 201 106; 29-33', ['USNM 201106']),
        ('USNM 200935b, c; 201025a; 201130; 201148; 203520b', ['USNM 200935B', 'USNM 200935C', 'USNM 201025A', 'USNM 201130', 'USNM 201148', 'USNM 203520B']),
        ('USNM type # 10660', ['USNM type no. 10660']),
        ('USNM Type No. 10660', ['USNM type no. 10660']),
        ('NMNH G4998-5003', ['NMNH G 4998', 'NMNH G 4999', 'NMNH G 5000', 'NMNH G 5001', 'NMNH G 5002', 'NMNH G 5003']),
        ('USNM # R12596', ['USNM R 12596']),
        ('USNM 234567-234571', ['USNM 234567', 'USNM 234568', 'USNM 234569', 'USNM 234570', 'USNM 234571']),
        ('USNM 123456 and 1234567', ['USNM 123456', 'USNM 1234567']),
        ('USNM No. 234567', ['USNM 234567']),
        ('USNM#123456', ['USNM 123456']),
        ('USNM #12345', ['USNM 12345']),
        ('USNM G3551-00', ['USNM G 3551-00']),
        ('NMNH 246892-3', ['NMNH 246892', 'NMNH 246893']),
        ('USNM 39958O', ['USNM 399580']),
        ('USNM 16215 16216 16217', ['USNM 16215', 'USNM 16216', 'USNM 16217']),
        ('USNM 12345 and RMA 12881', ['USNM 12345']),  # USNM RMA 12881 is not really a catalog number but matches the pattern
        ('USNM 117801 and G4800', ['USNM 117801', 'USNM G 4800']),
        ('USNM 83943b', ['USNM 83943B']),
        ('NMNH 123456-59', ['NMNH 123456', 'NMNH 123457', 'NMNH 123458', 'NMNH 123459']),
        ('USNM 123343b, d-f; 123344d-j', ['USNM 123343B', 'USNM 123343D', 'USNM 123343E', 'USNM 123343F', 'USNM 123344D', 'USNM 123344E', 'USNM 123344F', 'USNM 123344G', 'USNM 123344H', 'USNM 123344I', 'USNM 123344J']),
        ('type no. 44661 (USNM)', ['USNM type no. 44661']),
        ('USNM 123343a, c; 123344a, c', ['USNM 123343A', 'USNM 123343C', 'USNM 123344A', 'USNM 123344C']),
        ('USNM 201 1 16a', ['USNM 201116A']),
        ('NMNH specimens 112345 through 112348', ['NMNH 112345', 'NMNH 112346', 'NMNH 112347', 'NMNH 112348']),
        ('USNM 426-l and HU-1', ['USNM 426-1']),
        ('NMNH No. 11742-00, 11743-00, and 11745-00', ['NMNH 11742-00', 'NMNH 11743-00', 'NMNH 11745-00']),
        ('USNM 200961, 200982a, c, e, 201182a-e, 201183a, 201184', ['USNM 200961', 'USNM 200982A', 'USNM 200982C', 'USNM 200982E', 'USNM 201182A', 'USNM 201182B', 'USNM 201182C', 'USNM 201182D', 'USNM 201182E', 'USNM 201183A', 'USNM 201184']),
        ('...figured paratypes USNM 201 1 17, 201 1 19, 201 120, 201 123. Discussion...', ['USNM 201117', 'USNM 201119', 'USNM 201120', 'USNM 201123']),
        ('...8 holotype **USNM 76238; 1** P paratype **USNM 76239**...', ['USNM 76238', 'USNM 76239']),
        ('...bout 40 ° N. 70 °. **USNM 112700 112779-112783**. Actinoc...', ['USNM 112700', 'USNM 112779', 'USNM 112780', 'USNM 112781', 'USNM 112782', 'USNM 112783']),
        ('...Hypotypes figured by Cooper (1954) USNM 123358; 123359a-c; 123361a; 123363a; 123364; 123365a, b; 123366a, b; 123367; 123368a; 123369a; 123370a...', ['USNM 123358', 'USNM 123359A', 'USNM 123359B', 'USNM 123359C', 'USNM 123361A', 'USNM 123363A', 'USNM 123364', 'USNM 123365A', 'USNM 123365B', 'USNM 123366A', 'USNM 123366B', 'USNM 123367', 'USNM 123368A', 'USNM 123369A', 'USNM 123370A']),
        ('...of MHNJP 708 709 USNM 504332 571257 and 5 7 12 5 8 with sk...', ['USNM 504332', 'USNM 571257', 'USNM 571258']),
        ('...Unfigured Paratypes USNM 200901b-e, 201I29d-h...', ['USNM 200901B', 'USNM 200901C', 'USNM 200901D', 'USNM 200901E', 'USNM 201129D', 'USNM 201129E', 'USNM 201129F', 'USNM 201129G', 'USNM 201129H']),
        ('USNM 112686-112688 112729-112733 112735', ['USNM 112686', 'USNM 112687', 'USNM 112688', 'USNM 112729', 'USNM 112730', 'USNM 112731', 'USNM 112732', 'USNM 112733', 'USNM 112735']),
        ('USNM Coll. No. 23 1376 231377', ['USNM 231376', 'USNM 231377']),
        ('USNM Helminthol. Coll. No. 81445', ['USNM 81445']),
        ('USNM Helminthological Collection No. 75125', ['USNM 75125']),
        ('USNM mollusc coll. 123456', ['USNM 123456']),
        ('USNM B240-B243 and B245-B247', ['USNM B 240', 'USNM B 241', 'USNM B 242', 'USNM B 243', 'USNM B 245', 'USNM B 246', 'USNM B 247']),
        ('USNM type no. 4661 USNM type no. 4662', ['USNM type no. 4661', 'USNM type no. 4662']),
        ('USNM collection No. 74030', ['USNM 74030']),
        ('USNM Coll. No. 72339', ['USNM 72339']),
        ('USNM 192947-50 164359-60', ['USNM 164359', 'USNM 164360', 'USNM 192947', 'USNM 192948', 'USNM 192949', 'USNM 192950']),
        ('USNM 144786a', ['USNM 144786A']),
        #'USNM115418-22-2', ['USNM 115418', 'USNM 115419', 'USNM 115420', 'USNM 115421', 'USNM 115422']),
        ('USNMNo. 3883A-2', ['USNM 3883A-2']),
        ('USNM204287 204288', ['USNM 204287', 'USNM 204288']),
        ('Carapace USNM 528 543 (Pl. 3 Fig. 10a). Par...',  ['USNM 528543']),
        ('USNM 159331-2 165090', ['USNM 159331', 'USNM 159332', 'USNM 165090']),
        ('...97; 4 July 1984; USNM 23 4297 (paratype 1 ovigero...', ['USNM 234297']),
        ('USNM 222269--73 247305--11 247632--3 343241 268946--53', ['USNM 222269', 'USNM 222270', 'USNM 222271', 'USNM 222272', 'USNM 222273', 'USNM 247305', 'USNM 247306', 'USNM 247307', 'USNM 247308', 'USNM 247309', 'USNM 247310', 'USNM 247311', 'USNM 247632', 'USNM 247633', 'USNM 343241', 'USNM 268946', 'USNM 268947', 'USNM 268948', 'USNM 268949', 'USNM 268950', 'USNM 268951', 'USNM 268952', 'USNM 268953']),
        #'USNM5312-1 381-3 51-2 3 19 5 8': []
        ('USNM 3369 13823 345225 346582 489406', ['USNM 3369', 'USNM 13823', 'USNM 345225', 'USNM 346582', 'USNM 489406']),
        ('USNM 9731 1 - 13', ['USNM 97311', 'USNM 97312', 'USNM 97313']),
        ('USNM 1081 0.106 44.766', ['USNM 1081']),
        ('USNM 111240/52 USNM 113087 78-80 34-38 10-12 9 51', ['USNM 111240-52', 'USNM 113087']),
        ('NMNH 84021, ANSP 1832; 5', ['NMNH 84021']),
        ('NMNH 91234, UNAM 1808, MCZ 10807, 32868, UM 79938', ['NMNH 91234', 'MCZ 10807', 'MCZ 32868', 'MCZ UM 79938']),
        ('FMNH  22088, 22359, 161121, 216745, YPM 12870; O', ['FMNH 22088', 'FMNH 22088', 'FMNH 22359', 'FMNH 161121', 'FMNH 216745', 'YPM 12870']), # FMNH YPM 12870 is incorrect but acceptable by the parser at present
        ('USNM 12345, 12348, NMNH 12346, USNH 12347', ['USNM 12345', 'USNM 12348', 'NMNH 12346', 'USNH 12347']),
        ('USNM12345, 12346', ['USNM 12345', 'USNM 12346']),
        ('...Kentropyx calcarata FMNH 31352. 42523.  NMNH 292411. 292412. Lacerta lepida...', ['FMNH 31352', 'FMNH 42523', 'NMNH 292411', 'NMNH 292412']),
        ('...Maria Madre Island, AMNH 180522, NMNH  92413; "Tres Marias...', ['AMNH 180522', 'NMNH 92413']),
        ('...paratype (USNM 2i 1807), length...', ['USNM 211807']),
        ('...right valve (USNM  21,1812). length 7.0 mm, (d) left, valve (USNM 21,1815), length  7.0 mm...', ['USNM 211812', 'USNM 211815']),
        ('USNM 153541, loc. 2. 22, 23', ['USNM 153541']),
        ('USNM 153555, loc. 71. 14, 15', ['USNM 153555']),
        ('USNM 213781, pi. 6, fig. 5', ['USNM 213781']),
        ('USNM 8494[', ['USNM 8494']),
        ('MCZ 16840; CAS 50509, 52256-78', ['MCZ 16840']),
        ('USNM PAL 12345', ['USNM PAL 12345']),
        ('...Kanagawa, Yokohama (USNM 43067a, 3)...', ['USNM 43067A']),
        ('NMNH UCV4871', ['NMNH UCV 4871']),
        ('USNM 250984 - 3', ['USNM 250984']),
        ('USNM 150893-924', ['USNM 150893', 'USNM 150894', 'USNM 150895', 'USNM 150896', 'USNM 150897', 'USNM 150898', 'USNM 150899', 'USNM 150900', 'USNM 150901', 'USNM 150902', 'USNM 150903', 'USNM 150904', 'USNM 150905', 'USNM 150906', 'USNM 150907', 'USNM 150908', 'USNM 150909', 'USNM 150910', 'USNM 150911', 'USNM 150912', 'USNM 150913', 'USNM 150914', 'USNM 150915', 'USNM 150916', 'USNM 150917', 'USNM 150918', 'USNM 150919', 'USNM 150920', 'USNM 150921', 'USNM 150922', 'USNM 150923', 'USNM 150924']),
        ('USNM P4833, P4861, P4862 and P4863', ['USNM P 4833', 'USNM P 4861', 'USNM P 4862', 'USNM P 4863']),
        ('AMNH 1021, 3519, 3520', ['AMNH 1021', 'AMNH 3519', 'AMNH 3520']),
        ('NMNH 18279, Fig. lb', ['NMNH 18279']),
        #'FMNH 23-X-19B0': [FMNH 23-X-19B0]),  # not set up to handle values with no number
        ('USNM 97174-5, Behr, 1915', ['USNM 97174', 'USNM 97175']),
        ('USNM 14344.  lb', ['USNM 14344']),
        ('...Tobago. A. USNM 228125- B. USNM 228124. C. USNM 228123- D, E, F. South American mainland....', ['USNM 228125B', 'USNM 228124C', 'USNM 228123D', 'USNM 228123E', 'USNM 228123F']),
        ('USNM P4430a-d', ['USNM P 4430A', 'USNM P 4430B', 'USNM P 4430C', 'USNM P 4430D']),
        ('...legans), USNM 40886  (syntypes of Protaster miamiensis), USNM 87166 (syntypes of T.  meafordensis), USNM 92604, USNM 92607, USNM 92617, USNM  92627, USNM 92639, USNM 161520, NYSM 7784 (holotype of T.  schohariae), MCZ 470 (holotype of Protaster? gramdiferus; ex MCZ 21),  CSC 1404 (h...', ['USNM 40886', 'USNM 87166', 'USNM 92604', 'USNM 92607', 'USNM 92617', 'USNM 92627', 'USNM 92639', 'USNM 161520', 'MCZ 470', 'MCZ 21']),
        ('NMNH 194383-85/87/92/93/99', ['NMNH 194383', 'NMNH 194384', 'NMNH 194385', 'NMNH 194387', 'NMNH 194392', 'NMNH 194393', 'NMNH 194399']),
        ('Museum San Carlos olivine (USNM 111312/444). Moreover, Jeﬀcoate et al. (2007',  ['USNM 111312-444']),
        ('and USNM #113498, a Smithsonian natural basaltic glass', ['USNM 113498']),
        ('standards are a gem-quality meionite from Brazil, U.S.N.M. # R6600-1', ['USNM R 6600', 'USNM R 6601']),  # accetpable but incorrect
        ('451 Appendix Table 7. (Continued) USNM No, 496302 03 04 05 06 07 08 09 10 498278 79 498413 Date Collected Age Sex Remarks', ['USNM 496302', 'USNM 496303', 'USNM 496304', 'USNM 496305', 'USNM 496306', 'USNM 496307', 'USNM 496308', 'USNM 496309', 'USNM 496310', 'USNM 498278', 'USNM 498279', 'USNM 498413']),
        ('...USNM 118223. Santander: El Centro, USNM 144968-9; Finca El Mosco, near Lebrija...', ['USNM 118223', 'USNM 144968', 'USNM 144969']),
        ('...(Map 8); 3 (USNM 26192-93); 69 (USNM 153449-68, 153510-27); 70 (USNM 153486-509); 71 (USN...', ['USNM 153449', 'USNM 153450', 'USNM 153451', 'USNM 153452', 'USNM 153453', 'USNM 153454', 'USNM 153455', 'USNM 153456', 'USNM 153457', 'USNM 153458', 'USNM 153459', 'USNM 153460', 'USNM 153461', 'USNM 153462', 'USNM 153463', 'USNM 153464', 'USNM 153465', 'USNM 153466', 'USNM 153467', 'USNM 153468', 'USNM 153486', 'USNM 153487', 'USNM 153488', 'USNM 153489', 'USNM 153490', 'USNM 153491', 'USNM 153492', 'USNM 153493', 'USNM 153494', 'USNM 153495', 'USNM 153496', 'USNM 153497', 'USNM 153498', 'USNM 153499', 'USNM 153500', 'USNM 153501', 'USNM 153502', 'USNM 153503', 'USNM 153504', 'USNM 153505', 'USNM 153506', 'USNM 153507', 'USNM 153508', 'USNM 153509', 'USNM 153510', 'USNM 153511', 'USNM 153512', 'USNM 153513', 'USNM 153514', 'USNM 153515', 'USNM 153516', 'USNM 153517', 'USNM 153518', 'USNM 153519', 'USNM 153520', 'USNM 153521', 'USNM 153522', 'USNM 153523', 'USNM 153524', 'USNM 153525', 'USNM 153526', 'USNM 153527', 'USNM 26192', 'USNM 26193']),
        ('...few cervicals, but it also lacks the skull. Referred specimens USNM 7760, 7761, 8065, 8016, and 5031 are even more fragmentary, and...', ['USNM 5031', 'USNM 7760', 'USNM 7761', 'USNM 8016', 'USNM 8065']),
        ('...4 Aug 1979; j. D. Hardy, hunter in col 1ector. Stuvniva lilium USNM 00538023-63, St. John Parish, various localities, July, 1979; G...', ['USNM 538023', 'USNM 538023-5T', 'USNM 538024', 'USNM 538025', 'USNM 538026', 'USNM 538027', 'USNM 538028', 'USNM 538029', 'USNM 538030', 'USNM 538031', 'USNM 538032', 'USNM 538033', 'USNM 538034', 'USNM 538035', 'USNM 538036', 'USNM 538037', 'USNM 538038', 'USNM 538039', 'USNM 538040', 'USNM 538041', 'USNM 538042', 'USNM 538043', 'USNM 538044', 'USNM 538045', 'USNM 538046', 'USNM 538047', 'USNM 538048', 'USNM 538049', 'USNM 538050', 'USNM 538051', 'USNM 538052', 'USNM 538053', 'USNM 538054', 'USNM 538055', 'USNM 538056', 'USNM 538057', 'USNM 538058', 'USNM 538059', 'USNM 538060', 'USNM 538061', 'USNM 538062', 'USNM 538063']),
        ('...vindo NP), and Amnirana amnicola (310 km SE; nearest voucher is MCZ A-139750, Ivindo NP). Laurent (1951) reported Hyperolius steind...', ['MCZ A 139750']),
        ('...9-72; Sri Lanka: nr. Negombo Point, Pitipana Fisheries Station, USNM 192727; Puttalam, AMNH 94493; Jaffna Lagoon, FMNH 121498-499; A...', ['AMNH 94493', 'FMNH 121498', 'FMNH 121499', 'USNM 192727']),
        ('...FMNH 2061 14. Barisia imbricata NMNH 32166. Basiliscus basiliscus FMNH 164...', ['FMNH 164', 'FMNH 206114', 'NMNH 32166']),
        ('...21, 1968 from the same locality; USNM 192877 is a male collected on June 30, 1968...', ['USNM 192877']),
        ('USNM 113027/43, 113027/353, 113028/0103, 113028/05', ['USNM 113027-353', 'USNM 113027-43', 'USNM 113028-0103', 'USNM 113028-05']),
        ('..Junin: Same data as holotype: FMNH 34242/1-23, 34247, 11 males, 4 females, 9 juveniles...', ['FMNH 34242-1', 'FMNH 34242-10', 'FMNH 34242-11', 'FMNH 34242-12', 'FMNH 34242-13', 'FMNH 34242-14', 'FMNH 34242-15', 'FMNH 34242-16', 'FMNH 34242-17', 'FMNH 34242-18', 'FMNH 34242-19', 'FMNH 34242-2', 'FMNH 34242-20', 'FMNH 34242-21', 'FMNH 34242-22', 'FMNH 34242-23', 'FMNH 34242-3', 'FMNH 34242-4', 'FMNH 34242-5', 'FMNH 34242-6', 'FMNH 34242-7', 'FMNH 34242-8', 'FMNH 34242-9', 'FMNH 34247']),
        # No results expected
        ('NMNH 1234567890', []),
        ('Dyak coll. 190010408-9 (USNM)', []),
        # Incomplete results
        #("...Philippines: Luzon, Camarines Province, Lake Buhi, cas 60947; USNM 1197697-98, 197844M8, 197851-197857. No data: bmnh 1946.1.7.24-...", [])
    ],
)
def test_parse_numbers(test_input, expected):
    assert set(Parser().parse(test_input)) == set(expected)




@pytest.mark.parametrize(
    'test_input,expected_ranged,expected_unranged',
    [
        ("LL4 (S3)1,3 L/LL4 (S1)2,3 H4 (S3)2  USNM 1240-4, 5, 6 USNM 610-2",
         ['USNM 1240', 'USNM 1241', 'USNM 1242', 'USNM 1243', 'USNM 1244', 'USNM 1245', 'USNM 1246', 'USNM 610', 'USNM 611', 'USNM 612'],
         ['USNM 1240-4', 'USNM 1240-5', 'USNM 1240-6', 'USNM 610-2']),
    ],
)
def test_parse_ranged(test_input, expected_ranged, expected_unranged):
    assert set(Parser(True).parse(test_input)) == set(expected_ranged)
    assert set(Parser(False).parse(test_input)) == set(expected_unranged)
